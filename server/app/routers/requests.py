import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..daily_time import adjust_today
from ..models import TimeRequest, Child
from ..websocket_manager import manager

router = APIRouter(prefix="/requests", tags=["Time Extension Requests"])


class CreateTimeRequestSchema(BaseModel):
    child_id: int = Field(default=1, description="ID của trẻ")
    device_id: Optional[str] = Field(default=None, description="Device GUID")
    requested_minutes: int = Field(default=15, ge=5, le=180, description="Số phút xin thêm")
    reason: str = Field(default="Em xin thêm thời gian làm bài tập", max_length=255)


class ApproveRequestSchema(BaseModel):
    duration_min: Optional[int] = Field(default=None, ge=5, le=180, description="Số phút phê duyệt cấp thêm")


@router.get("/")
def get_all_requests(
    child_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Lấy danh sách các yêu cầu xin thêm giờ (Approval Center)."""
    query = db.query(TimeRequest)
    if child_id:
        query = query.filter(TimeRequest.child_id == child_id)
    if status:
        query = query.filter(TimeRequest.status == status)
    
    requests = query.order_by(TimeRequest.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "child_id": r.child_id,
            "device_id": r.device_id,
            "requested_minutes": r.requested_minutes,
            "reason": r.reason,
            "status": r.status,
            "granted_minutes": r.granted_minutes,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
        }
        for r in requests
    ]


@router.get("/{child_id}")
def get_child_requests(child_id: int, db: Session = Depends(get_db)):
    """Lấy danh sách yêu cầu của một trẻ cụ thể."""
    return get_all_requests(child_id=child_id, status=None, db=db)


@router.post("/")
async def create_time_request(req: CreateTimeRequestSchema, db: Session = Depends(get_db)):
    """Trẻ gửi yêu cầu xin thêm giờ từ máy con."""
    new_req = TimeRequest(
        child_id=req.child_id,
        device_id=req.device_id,
        requested_minutes=req.requested_minutes,
        reason=req.reason,
        status="pending",
        created_at=datetime.datetime.utcnow()
    )
    db.add(new_req)
    db.commit()
    db.refresh(new_req)
    await manager.send_to_parents({
        "cmd": "new_time_request",
        "child_id": new_req.child_id,
        "request_id": new_req.id,
    })
    return {"status": "success", "request_id": new_req.id, "message": "Yêu cầu đã được gửi tới phụ huynh"}


@router.post("/{request_id}/approve")
async def approve_time_request(
    request_id: int,
    body: Optional[ApproveRequestSchema] = None,
    db: Session = Depends(get_db)
):
    """Phụ huynh duyệt yêu cầu xin thêm giờ (+15p / +30p)."""
    req = db.query(TimeRequest).filter(TimeRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Không tìm thấy yêu cầu")

    granted = (body.duration_min if body and body.duration_min else req.requested_minutes) or 15
    if req.status != "pending":
        raise HTTPException(status_code=409, detail="Yêu cầu đã được xử lý")
    req.status = "approved"
    req.granted_minutes = granted
    req.resolved_at = datetime.datetime.utcnow()

    adjust_today(db, req.child_id, granted)
    db.commit()
    await manager.broadcast({
        "cmd": "extend_time",
        "child_id": req.child_id,
        "granted_minutes": granted,
        "reason": f"Phụ huynh duyệt thêm {granted} phút",
    })

    return {
        "status": "success",
        "request_id": req.id,
        "granted_minutes": granted,
        "message": f"Đã duyệt thêm {granted} phút thành công"
    }


@router.post("/{request_id}/reject")
async def reject_time_request(request_id: int, db: Session = Depends(get_db)):
    """Phụ huynh từ chối yêu cầu xin thêm giờ."""
    req = db.query(TimeRequest).filter(TimeRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Không tìm thấy yêu cầu")

    if req.status != "pending":
        raise HTTPException(status_code=409, detail="Yêu cầu đã được xử lý")
    req.status = "rejected"
    req.resolved_at = datetime.datetime.utcnow()
    db.commit()

    # Báo cho Agent qua WebSocket nếu cần
    await manager.broadcast({
        "cmd": "request_rejected",
        "request_id": req.id,
        "reason": "Phụ huynh chưa đồng ý cấp thêm thời gian"
    })

    return {
        "status": "success",
        "request_id": req.id,
        "message": "Đã từ chối yêu cầu"
    }

