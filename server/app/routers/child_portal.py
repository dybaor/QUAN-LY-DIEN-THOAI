"""API dành riêng cho cổng học tập của trẻ (vai trò child-view): chỉ đọc dữ liệu của chính trẻ."""

from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import case, func
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from .. import audit, config
from ..database import get_db
from ..deps import Principal, client_ip, create_session, require_child, revoke_session
from ..models import ROLE_CHILD, AccessHistoryLog, AuditLog, Child, ChildWindowLock, EnrollmentCode, WebDailyUsage
from ..security import hash_secret, verify_secret
from ..services import get_or_create_policy, is_paused, policy_payload, time_snapshot
from ..websocket_manager import manager
from .auth import enforce_rate_limit, lock_remaining, login_limiter, pin_limiter
from .policy_events import EventCreateSchema, add_event, ingest_events
from .reports import today_activity
from .requests import create_request

router = APIRouter(prefix="/api/child", tags=["Cổng học tập của trẻ"])


class PairSchema(BaseModel):
    code: str = Field(..., min_length=8, max_length=8)


class VerifyPinSchema(BaseModel):
    pin: str = Field(..., max_length=6)
    unlock_window: bool = True


class AccessLogSchema(BaseModel):
    target_name: str = Field(..., max_length=255)
    target_type: str = Field(default="Trang web", max_length=50)
    status: str = Field(default="allowed", pattern="^(allowed|blocked)$")


class TimeRequestSchema(BaseModel):
    requested_minutes: int = Field(default=15, ge=5, le=180)
    reason: str = Field(default="Em xin thêm thời gian làm bài tập", max_length=255)


def session_payload(db: Session, child: Child, principal_session) -> dict:
    policy = get_or_create_policy(db, child)
    return {
        "child_id": child.id,
        "child_name": child.name or "",
        "is_initialized": bool(child.name and policy.lock_password_hash),
        "csrf_token": principal_session.csrf_token,
    }


@router.post("/pair")
def pair_portal(req: PairSchema, request: Request, response: Response, db: Session = Depends(get_db)):
    """Ghép đôi cổng học tập bằng mã 8 ký tự phụ huynh tạo trên dashboard."""
    enforce_rate_limit(login_limiter, request)
    entry = db.query(EnrollmentCode).filter(EnrollmentCode.code == req.code.strip().upper(),
                                            EnrollmentCode.is_used.is_(False)).first()
    if not entry or entry.expires_at < datetime.utcnow():
        raise HTTPException(400, "Mã ghép đôi không hợp lệ hoặc đã hết hạn")
    entry.is_used = True
    child = db.get(Child, entry.child_id)
    session = create_session(db, response, request, role=ROLE_CHILD, child_id=child.id)
    audit.record(db, Principal(ROLE_CHILD, child_id=child.id, name=child.name), "portal_paired",
                 child_id=child.id, ip=client_ip(request), new={"method": "Mã ghép đôi"}, commit=True)
    return session_payload(db, child, session)


@router.get("/session")
def get_session(principal: Principal = Depends(require_child), db: Session = Depends(get_db)):
    return session_payload(db, db.get(Child, principal.child_id), principal.session)


@router.post("/logout")
def logout_portal(response: Response, principal: Principal = Depends(require_child), db: Session = Depends(get_db)):
    revoke_session(db, principal.session)
    response.delete_cookie(config.CHILD_SESSION_COOKIE, path="/")
    return {"status": "success"}


@router.get("/policy")
def get_policy(principal: Principal = Depends(require_child), db: Session = Depends(get_db)):
    return policy_payload(db, get_or_create_policy(db, db.get(Child, principal.child_id)))


@router.get("/web-usage")
def get_usage(principal: Principal = Depends(require_child), db: Session = Depends(get_db)):
    return time_snapshot(principal.child_id, datetime.now().date(), db)


@router.post("/web-usage")
def track_usage(principal: Principal = Depends(require_child), db: Session = Depends(get_db)):
    """Nhịp đếm giờ của cổng học tập (mỗi 5 giây). Không đếm khi đang khóa, hết giờ hoặc tạm nghỉ."""
    child = db.get(Child, principal.child_id)
    policy = get_or_create_policy(db, child)
    now = datetime.now()
    snapshot = time_snapshot(child.id, now.date(), db)
    initialized = bool(child.name and policy.lock_password_hash)
    if (initialized and not snapshot["lock_reason"] and not snapshot["schedule_blocked"]
            and snapshot["remaining_seconds"] > 0 and not is_paused(policy)):
        sample = insert(WebDailyUsage).values(child_id=child.id, day=now.date(), used_seconds=0, last_seen=now.timestamp())
        gap = sample.excluded.last_seen - WebDailyUsage.last_seen
        db.execute(sample.on_conflict_do_update(
            index_elements=[WebDailyUsage.child_id, WebDailyUsage.day],
            set_={
                "used_seconds": WebDailyUsage.used_seconds + case((gap.between(0, 12), gap), else_=0),
                "last_seen": func.max(WebDailyUsage.last_seen, sample.excluded.last_seen),
            },
        ))
        db.commit()
    return time_snapshot(child.id, now.date(), db)


@router.post("/verify-pin")
async def verify_pin(req: VerifyPinSchema, request: Request, principal: Principal = Depends(require_child),
                     db: Session = Depends(get_db)):
    """Mở khóa bằng PIN phụ huynh: Argon2id, khóa 15 phút sau 5 lần sai, giới hạn tần suất theo IP."""
    enforce_rate_limit(pin_limiter, request)
    child = db.get(Child, principal.child_id)
    policy = get_or_create_policy(db, child)
    if not policy.lock_password_hash:
        return {"valid": False, "message": "Chưa có mã PIN phụ huynh nào được thiết lập!"}
    wait = lock_remaining(policy.pin_locked_until)
    if wait:
        raise HTTPException(status.HTTP_423_LOCKED, f"Nhập sai quá nhiều lần. Thử lại sau {-(-wait // 60)} phút.")
    valid, rehash = verify_secret(policy.lock_password_hash, req.pin.strip())
    add_event(db, child.id, "web-portal", "unlock_request", "Nhập mã PIN mở khóa" + ("" if valid else " (sai)"), policy.id)
    if not valid:
        policy.pin_failed_count = (policy.pin_failed_count or 0) + 1
        if policy.pin_failed_count >= config.MAX_FAILED_LOGINS:
            policy.pin_failed_count = 0
            policy.pin_locked_until = datetime.utcnow() + timedelta(minutes=config.LOCKOUT_MINUTES)
            audit.record(db, principal, "pin_locked", child_id=child.id, ip=client_ip(request))
        db.commit()
        return {"valid": False, "message": "Mã PIN không chính xác. Vui lòng thử lại!"}
    policy.pin_failed_count = 0
    if rehash:
        policy.lock_password_hash = hash_secret(req.pin.strip())
    if req.unlock_window and db.get(ChildWindowLock, child.id):
        db.query(ChildWindowLock).filter_by(child_id=child.id).delete()
        audit.record(db, principal, "unlocked_by_pin", child_id=child.id, ip=client_ip(request))
    db.commit()
    await manager.notify_child({"cmd": "unlock_window", "child_id": child.id, "reason": "Mở khóa bằng mã PIN"}, child.id)
    return {"valid": True, "message": "Xác thực thành công"}


@router.post("/access-log")
def create_access_log(req: AccessLogSchema, principal: Principal = Depends(require_child), db: Session = Depends(get_db)):
    log = AccessHistoryLog(child_id=principal.child_id, device_id="web-portal", ts=datetime.utcnow(),
                           target_name=req.target_name.strip(), target_type=req.target_type.strip(), status=req.status)
    db.add(log)
    is_app = req.target_type == "Ứng dụng"
    event_type = ("app_start" if is_app else "domain_query") if req.status == "allowed" else ("blocked_app" if is_app else "blocked_domain")
    # Sự kiện chuẩn chỉ lưu tên miền cấp 2, không lưu nội dung trẻ tìm kiếm (nhật ký truy cập riêng của phụ huynh vẫn giữ)
    event_subject = "google.com" if req.target_type == "Tìm kiếm" else log.target_name
    add_event(db, principal.child_id, "web-portal", event_type, event_subject, ts=log.ts)
    db.commit()
    return {"status": "success", "id": log.id}


@router.post("/events")
async def create_events(items: List[EventCreateSchema], request: Request, principal: Principal = Depends(require_child),
                        db: Session = Depends(get_db)):
    return await ingest_events(db, principal, items[:50], request)


@router.post("/time-requests")
async def create_time_request(req: TimeRequestSchema, principal: Principal = Depends(require_child),
                              db: Session = Depends(get_db)):
    entry = await create_request(db, principal.child_id, "web-portal", req.requested_minutes, req.reason)
    return {"status": "success", "request_id": entry.id, "message": "Yêu cầu đã được gửi tới phụ huynh"}


@router.get("/today")
def get_today(principal: Principal = Depends(require_child), db: Session = Depends(get_db)):
    """Màn hình minh bạch "Hôm nay em đã dùng gì"."""
    return today_activity(db, principal.child_id)


@router.get("/audit-log")
def get_audit_log(limit: int = 50, principal: Principal = Depends(require_child), db: Session = Depends(get_db)):
    """Trẻ được xem nhật ký thay đổi cấu hình của ba mẹ (nguyên tắc NT5)."""
    entries = (db.query(AuditLog).filter(AuditLog.child_id == principal.child_id)
               .order_by(AuditLog.ts.desc()).limit(min(limit, 200)).all())
    return [{key: value for key, value in audit.serialize(e).items() if key != "client_ip"} for e in entries]
