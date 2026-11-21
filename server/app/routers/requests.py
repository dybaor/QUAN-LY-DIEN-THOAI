import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import audit
from ..daily_time import adjust_today
from ..database import get_db
from ..deps import Principal, authorize_child, client_ip, owned_child_ids, require_parent
from ..models import TimeRequest
from ..websocket_manager import manager
from .policy_events import add_event

router = APIRouter(prefix="/requests", tags=["Time Extension Requests"])


class ApproveRequestSchema(BaseModel):
    duration_min: Optional[int] = Field(default=None, ge=5, le=180, description="Số phút phê duyệt cấp thêm")


def serialize(r: TimeRequest) -> dict:
    return {
        "id": r.id, "child_id": r.child_id, "device_id": r.device_id, "requested_minutes": r.requested_minutes,
        "reason": r.reason, "status": r.status, "granted_minutes": r.granted_minutes,
        "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
        "resolved_at": r.resolved_at.isoformat() + "Z" if r.resolved_at else None,
    }


async def create_request(db: Session, child_id: int, device_id: Optional[str], minutes: int, reason: str) -> TimeRequest:
    """Trẻ gửi yêu cầu xin thêm giờ (từ cổng học tập hoặc Agent)."""
    entry = TimeRequest(child_id=child_id, device_id=device_id, requested_minutes=minutes, reason=reason,
                        status="pending", created_at=datetime.datetime.utcnow())
    db.add(entry)
    add_event(db, child_id, device_id or "web-portal", "unlock_request", f"Xin thêm {minutes} phút: {reason}")
    db.commit()
    db.refresh(entry)
    await manager.send_to_parents({"cmd": "new_time_request", "child_id": child_id, "request_id": entry.id}, child_id)
    return entry


def _load_owned(db: Session, principal: Principal, request_id: int) -> TimeRequest:
    entry = db.get(TimeRequest, request_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Không tìm thấy yêu cầu")
    authorize_child(db, principal, entry.child_id)
    if entry.status != "pending":
        raise HTTPException(status_code=409, detail="Yêu cầu đã được xử lý")
    return entry


@router.get("/")
def get_all_requests(child_id: Optional[int] = None, status: Optional[str] = None,
                     principal: Principal = Depends(require_parent), db: Session = Depends(get_db)):
    ids = [authorize_child(db, principal, child_id).id] if child_id else owned_child_ids(db, principal)
    query = db.query(TimeRequest).filter(TimeRequest.child_id.in_(ids))
    if status:
        query = query.filter(TimeRequest.status == status)
    return [serialize(r) for r in query.order_by(TimeRequest.created_at.desc()).limit(200).all()]


@router.get("/{child_id}")
def get_child_requests(child_id: int, principal: Principal = Depends(require_parent), db: Session = Depends(get_db)):
    return get_all_requests(child_id=child_id, status=None, principal=principal, db=db)


@router.post("/{request_id}/approve")
async def approve_time_request(request_id: int, request: Request, body: Optional[ApproveRequestSchema] = None,
                               principal: Principal = Depends(require_parent), db: Session = Depends(get_db)):
    entry = _load_owned(db, principal, request_id)
    granted = (body.duration_min if body and body.duration_min else entry.requested_minutes) or 15
    entry.status = "approved"
    entry.granted_minutes = granted
    entry.resolved_at = datetime.datetime.utcnow()
    adjust_today(db, entry.child_id, granted)
    add_event(db, entry.child_id, "parent-dashboard", "override_granted", f"Duyệt thêm {granted} phút")
    audit.record(db, principal, "request_approved", child_id=entry.child_id, ip=client_ip(request),
                 new={"request_id": entry.id, "minutes": granted})
    db.commit()
    await manager.notify_child({"cmd": "extend_time", "child_id": entry.child_id, "granted_minutes": granted,
                                "reason": f"Phụ huynh duyệt thêm {granted} phút"}, entry.child_id)
    return {"status": "success", "request_id": entry.id, "granted_minutes": granted,
            "message": f"Đã duyệt thêm {granted} phút thành công"}


@router.post("/{request_id}/reject")
async def reject_time_request(request_id: int, request: Request, principal: Principal = Depends(require_parent),
                              db: Session = Depends(get_db)):
    entry = _load_owned(db, principal, request_id)
    entry.status = "rejected"
    entry.resolved_at = datetime.datetime.utcnow()
    audit.record(db, principal, "request_rejected", child_id=entry.child_id, ip=client_ip(request),
                 new={"request_id": entry.id})
    db.commit()
    await manager.send_to_child_devices({"cmd": "request_rejected", "child_id": entry.child_id, "request_id": entry.id,
                                         "reason": "Phụ huynh chưa đồng ý cấp thêm thời gian"}, entry.child_id)
    return {"status": "success", "request_id": entry.id, "message": "Đã từ chối yêu cầu"}
