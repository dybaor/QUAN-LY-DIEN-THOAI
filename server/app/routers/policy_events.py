from datetime import datetime, timedelta
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from .. import audit, config
from ..categories import normalize_categories
from ..daily_time import adjust_today
from ..database import get_db
from ..deps import (
    Principal, authorize_child, client_ip, require_admin, require_device, require_parent,
)
from ..models import (
    AccessHistoryLog, AgentDailyUsage, AuditLog, ChildWindowLock, DailyTimeAdjustment, DeviceEvent,
    MonitoringSession, TimeRequest, WebDailyUsage,
)
from ..services import (
    VIOLATION_TYPES, daily_usage_seconds, local_text, get_or_create_policy, normalize_event_type, normalize_schedule,
    policy_payload, time_snapshot,
)
from ..websocket_manager import manager

router = APIRouter(tags=["Policies & Events"])


# ==========================================
# SCHEMAS
# ==========================================
class DeductTimeSchema(BaseModel):
    child_id: int
    deduct_min: int = Field(default=15, ge=1, le=480, description="Số phút cần trừ bớt")
    reason: str = Field(default="Phụ huynh trừ bớt thời gian giải trí", max_length=255)


class PolicyUpdateSchema(BaseModel):
    child_id: int
    daily_quota_weekday_min: int = Field(ge=0, le=1440, description="Phút ngày thường")
    daily_quota_weekend_min: int = Field(ge=0, le=1440, description="Phút cuối tuần")
    schedule_matrix: Optional[str] = None
    blocked_apps: Optional[str] = None
    blocked_domains: Optional[str] = None
    blocked_categories: Optional[str] = None

    @field_validator("schedule_matrix")
    @classmethod
    def validate_schedule_matrix(cls, value):
        return normalize_schedule(value) if value is not None else value

    @field_validator("blocked_categories")
    @classmethod
    def validate_categories(cls, value):
        return normalize_categories(value) if value is not None else value


class PauseSchema(BaseModel):
    child_id: int
    minutes: int = Field(default=config.PAUSE_MAX_MINUTES, ge=5, le=config.PAUSE_MAX_MINUTES)


class LaunchAppSchema(BaseModel):
    app_id: str = Field(..., description="Mã ứng dụng muốn mở: calc, notepad, paint, wordpad")


class EventCreateSchema(BaseModel):
    ts: datetime
    device_id: Optional[str] = None
    child_id: Optional[int] = None
    type: str
    subject: str = Field(..., max_length=255)
    duration_sec: int = Field(default=0, ge=0, le=86400)
    policy_id: Optional[int] = None
    idempotency_key: Optional[str] = Field(default=None, max_length=64)


class MonitoringStartSchema(BaseModel):
    child_id: int
    device_id: str = "web-portal"


class MonitoringStopSchema(BaseModel):
    child_id: int
    session_id: Optional[int] = None


# ==========================================
# 1. CHÍNH SÁCH
# ==========================================
POLICY_FIELDS = ("daily_quota_weekday_min", "daily_quota_weekend_min", "schedule_matrix",
                 "blocked_apps", "blocked_domains", "blocked_categories")


@router.get("/policy/{child_id}")
def get_child_policy(child_id: int, principal: Principal = Depends(require_parent), db: Session = Depends(get_db)):
    child = authorize_child(db, principal, child_id)
    return policy_payload(db, get_or_create_policy(db, child))


@router.put("/policy/update")
async def update_policy(req: PolicyUpdateSchema, request: Request, principal: Principal = Depends(require_parent),
                        db: Session = Depends(get_db)):
    """Cập nhật chính sách, tăng version, ghi audit log và báo Agent đồng bộ ngay."""
    child = authorize_child(db, principal, req.child_id)
    policy = get_or_create_policy(db, child)
    before = {field: getattr(policy, field) for field in POLICY_FIELDS}
    before["schedule_matrix"] = normalize_schedule(before["schedule_matrix"] or "1" * 336)
    policy.daily_quota_weekday_min = req.daily_quota_weekday_min
    policy.daily_quota_weekend_min = req.daily_quota_weekend_min
    for field in ("schedule_matrix", "blocked_apps", "blocked_domains", "blocked_categories"):
        value = getattr(req, field)
        if value is not None:
            setattr(policy, field, value)
    after = {field: getattr(policy, field) for field in POLICY_FIELDS}
    old, new = audit.diff(before, after)
    if new:
        policy.version += 1
        policy.updated_at = datetime.utcnow()
        audit.record(db, principal, "policy_updated", child_id=child.id, ip=client_ip(request), old=old, new=new)
    db.commit()
    db.refresh(policy)
    await manager.send_to_child_devices({"cmd": "sync_policy", "child_id": child.id, "version": policy.version}, child.id)
    return {"status": "success", "policy_version": policy.version}


@router.post("/policy/deduct-time")
async def deduct_child_time(req: DeductTimeSchema, request: Request, principal: Principal = Depends(require_parent),
                            db: Session = Depends(get_db)):
    child = authorize_child(db, principal, req.child_id)
    policy = get_or_create_policy(db, child)
    remaining = time_snapshot(child.id, datetime.now().date(), db)["remaining_seconds"]
    deducted = min(req.deduct_min, (remaining + 59) // 60)
    if deducted:
        adjust_today(db, child.id, -deducted)
        audit.record(db, principal, "time_deducted", child_id=child.id, ip=client_ip(request),
                     new={"minutes": deducted, "reason": req.reason})
    db.commit()
    await manager.notify_child({
        "cmd": "time_deducted", "child_id": child.id, "deduct_min": deducted, "reason": req.reason,
        "adjustment_date": datetime.now().date().isoformat(),
    }, child.id)
    return {"status": "success", "deducted_minutes": deducted, "policy_version": policy.version,
            "message": f"Đã giảm {deducted} phút của trẻ"}


@router.post("/policy/pause")
async def start_parent_pause(req: PauseSchema, request: Request, principal: Principal = Depends(require_parent),
                             db: Session = Depends(get_db)):
    """Chế độ tạm nghỉ của phụ huynh: tạm ngưng giới hạn tối đa 2 giờ, có ghi audit log."""
    child = authorize_child(db, principal, req.child_id)
    policy = get_or_create_policy(db, child)
    policy.paused_until = datetime.utcnow() + timedelta(minutes=req.minutes)
    policy.version += 1
    add_event(db, child.id, "parent-dashboard", "override_granted", f"Tạm nghỉ giới hạn {req.minutes} phút", policy.id)
    audit.record(db, principal, "parent_pause_started", child_id=child.id, ip=client_ip(request),
                 new={"minutes": req.minutes, "until": policy.paused_until.isoformat() + "Z"})
    db.commit()
    payload = policy_payload(db, policy)
    await manager.notify_child({"cmd": "sync_policy", "child_id": child.id, "version": policy.version,
                                "paused_until": payload["paused_until"]}, child.id)
    return {"status": "success", "paused_until": payload["paused_until"]}


@router.delete("/policy/pause/{child_id}")
async def end_parent_pause(child_id: int, request: Request, principal: Principal = Depends(require_parent),
                           db: Session = Depends(get_db)):
    child = authorize_child(db, principal, child_id)
    policy = get_or_create_policy(db, child)
    if policy.paused_until:
        policy.paused_until = None
        policy.version += 1
        audit.record(db, principal, "parent_pause_ended", child_id=child.id, ip=client_ip(request))
        db.commit()
    await manager.notify_child({"cmd": "sync_policy", "child_id": child.id, "version": policy.version,
                                "paused_until": None}, child.id)
    return {"status": "success"}


# ==========================================
# 2. GIÁM SÁT MÀN HÌNH & LỊCH SỬ TRUY CẬP
# ==========================================
@router.post("/agent/launch-app")
def launch_desktop_app(req: LaunchAppSchema):
    """Mô phỏng mở ứng dụng an toàn cho trẻ — không khởi chạy phần mềm thật trên Windows."""
    app_whitelist = {
        "calc": "Máy tính Casio", "calculator": "Máy tính Casio", "notepad": "Sổ tay Ghi chú",
        "paint": "MS Paint Vẽ hình", "mspaint": "MS Paint Vẽ hình", "wordpad": "WordPad Soạn thảo",
        "write": "WordPad Soạn thảo", "osk": "Bàn phím ảo",
    }
    app_key = req.app_id.strip().lower()
    if app_key not in app_whitelist:
        raise HTTPException(status_code=400, detail=f"Ứng dụng '{req.app_id}' không nằm trong danh mục được phép mở an toàn.")
    return {"status": "success", "app_id": app_key, "app_name": app_whitelist[app_key],
            "message": f"Đang mô phỏng ứng dụng {app_whitelist[app_key]}"}


@router.post("/api/monitoring/start")
def start_monitoring_session(req: MonitoringStartSchema, request: Request, principal: Principal = Depends(require_parent),
                             db: Session = Depends(get_db)):
    child = authorize_child(db, principal, req.child_id)
    session = MonitoringSession(child_id=child.id, device_id=req.device_id, start_time=datetime.utcnow())
    db.add(session)
    audit.record(db, principal, "screen_view_requested", child_id=child.id, ip=client_ip(request))
    db.commit()
    db.refresh(session)
    return {"status": "success", "session_id": session.id, "start_time": local_text(session.start_time)}


@router.post("/api/monitoring/stop")
def stop_monitoring_session(req: MonitoringStopSchema, principal: Principal = Depends(require_parent),
                            db: Session = Depends(get_db)):
    child = authorize_child(db, principal, req.child_id)
    query = db.query(MonitoringSession).filter(MonitoringSession.child_id == child.id)
    if req.session_id:
        session = query.filter(MonitoringSession.id == req.session_id).first()
    else:
        session = query.filter(MonitoringSession.status == "Đang theo dõi").order_by(MonitoringSession.start_time.desc()).first()
    if not session:
        return {"status": "success", "duration_sec": 0, "message": "Không tìm thấy phiên cần đóng"}
    now = datetime.utcnow()
    session.end_time = now
    session.duration_sec = max(0, int((now - session.start_time).total_seconds()))
    session.status = "Đã kết thúc"
    db.commit()
    return {"status": "success", "session_id": session.id, "duration_sec": session.duration_sec,
            "end_time": local_text(now)}


@router.get("/api/monitoring/history/{child_id}")
def get_monitoring_history(child_id: int, limit: int = 30, principal: Principal = Depends(require_parent),
                           db: Session = Depends(get_db)):
    child = authorize_child(db, principal, child_id)
    sessions = (db.query(MonitoringSession).filter(MonitoringSession.child_id == child.id)
                .order_by(MonitoringSession.start_time.desc()).limit(min(limit, 200)).all())
    return [{
        "id": s.id,
        "start_time": local_text(s.start_time),
        "end_time": local_text(s.end_time) if s.end_time else "-",
        "duration": f"{s.duration_sec} giây" if s.duration_sec else ("Đang theo dõi" if s.status == "Đang theo dõi" else "-"),
        "status": s.status,
    } for s in sessions]


@router.get("/api/access-history/{child_id}")
def get_access_history(child_id: int, limit: int = 30, principal: Principal = Depends(require_parent),
                       db: Session = Depends(get_db)):
    child = authorize_child(db, principal, child_id)
    logs = (db.query(AccessHistoryLog).filter(AccessHistoryLog.child_id == child.id)
            .order_by(AccessHistoryLog.ts.desc()).limit(min(limit, 200)).all())
    return [{
        "id": log.id,
        "ts": local_text(log.ts),
        "target_name": log.target_name,
        "target_type": log.target_type,
        "status": log.status,
        "status_label": "✅ Hợp lệ" if log.status == "allowed" else "⛔ Bị chặn",
    } for log in logs]


# ==========================================
# 3. TIẾP NHẬN SỰ KIỆN 7 TRƯỜNG (CÓ KHÓA CHỐNG TRÙNG)
# ==========================================
def add_event(db: Session, child_id: int, device_id: str, event_type: str, subject: str,
              policy_id: Optional[int] = None, duration_sec: int = 0, key: Optional[str] = None,
              ts: Optional[datetime] = None) -> bool:
    """Ghi một sự kiện; trả về False nếu khóa chống trùng đã tồn tại (gửi bù sau khi mất mạng)."""
    statement = insert(DeviceEvent).values(
        ts=ts or datetime.utcnow(), device_id=device_id, child_id=child_id, type=event_type,
        subject=subject[:255], duration_sec=duration_sec, policy_id=policy_id, idempotency_key=key,
    ).on_conflict_do_nothing()
    return db.execute(statement).rowcount > 0


async def ingest_events(db: Session, principal: Principal, items: List[EventCreateSchema], request: Request) -> dict:
    device_id = principal.device_id or "web-portal"
    accepted, duplicates, rejected = 0, 0, 0
    alerts = []
    for item in items:
        if item.type == "clock_tamper":
            audit.record(db, principal, "clock_tamper", child_id=principal.child_id, ip=client_ip(request),
                         new={"detail": item.subject, "skew_sec": item.duration_sec})
            accepted += 1
            continue
        event_type = normalize_event_type(item.type)
        if not event_type:
            rejected += 1
            continue
        ts = item.ts if item.ts.tzinfo is None else datetime.utcfromtimestamp(item.ts.timestamp())
        if add_event(db, principal.child_id, device_id, event_type, item.subject, item.policy_id,
                     item.duration_sec, item.idempotency_key, ts):
            accepted += 1
            if event_type in VIOLATION_TYPES or event_type == "quota_warning":
                alerts.append({"type": event_type, "subject": item.subject})
        else:
            duplicates += 1
    db.commit()
    for alert in alerts:
        await manager.send_to_parents({"cmd": "violation_toast", "child_id": principal.child_id, **alert,
                                       "message": f"{alert['subject']} ({alert['type']})"}, principal.child_id)
        if principal.device_id and alert["type"] in ("blocked_app", "blocked_domain"):
            # Agent không mở popup hệ điều hành: lý do chặn hiển thị cho trẻ ngay trong Cổng học tập
            what = "Ứng dụng" if alert["type"] == "blocked_app" else "Trang web"
            await manager.send_to_children({
                "cmd": "violation_toast", "child_id": principal.child_id, "type": alert["type"],
                "message": f"{what} {alert['subject']} nằm trong danh sách ba mẹ đã chặn nên đã bị đóng lại."},
                principal.child_id)
    return {"status": "success", "recorded_count": accepted, "duplicate_count": duplicates, "rejected_count": rejected}


@router.post("/events/", status_code=status.HTTP_201_CREATED)
async def receive_events(event_data: Union[EventCreateSchema, List[EventCreateSchema]], request: Request,
                         principal: Principal = Depends(require_device), db: Session = Depends(get_db)):
    items = event_data if isinstance(event_data, list) else [event_data]
    return await ingest_events(db, principal, items[:500], request)


@router.post("/events/batch", status_code=status.HTTP_201_CREATED)
async def receive_events_batch(events: List[EventCreateSchema], request: Request,
                               principal: Principal = Depends(require_device), db: Session = Depends(get_db)):
    return await ingest_events(db, principal, events[:500], request)


@router.get("/events/violations/{child_id}")
def get_violation_events(child_id: int, limit: int = 50, principal: Principal = Depends(require_parent),
                         db: Session = Depends(get_db)):
    child = authorize_child(db, principal, child_id)
    events = (db.query(DeviceEvent).filter(DeviceEvent.child_id == child.id, DeviceEvent.type.in_(VIOLATION_TYPES))
              .order_by(DeviceEvent.ts.desc()).limit(min(limit, 200)).all())
    actions = {"blocked_app": "Đã dừng tiến trình", "blocked_domain": "Đã chặn truy cập", "locked": "Đã khóa máy"}
    return [{
        "id": e.id, "ts": local_text(e.ts), "device_id": e.device_id, "type": e.type,
        "subject": e.subject, "duration_sec": e.duration_sec, "action": actions[e.type],
    } for e in events]


# ==========================================
# 4. VÒNG ĐỜI DỮ LIỆU (NĐ 13/2023)
# ==========================================
def purge_older_than(db: Session, days: int = config.RETENTION_DAYS) -> int:
    cutoff = datetime.utcnow() - timedelta(days=days)
    cutoff_day = (datetime.now() - timedelta(days=days)).date()
    deleted = db.query(DeviceEvent).filter(DeviceEvent.ts < cutoff).delete(synchronize_session=False)
    deleted += db.query(AccessHistoryLog).filter(AccessHistoryLog.ts < cutoff).delete(synchronize_session=False)
    deleted += db.query(MonitoringSession).filter(MonitoringSession.start_time < cutoff).delete(synchronize_session=False)
    deleted += db.query(TimeRequest).filter(TimeRequest.created_at < cutoff).delete(synchronize_session=False)
    deleted += db.query(AuditLog).filter(AuditLog.ts < cutoff).delete(synchronize_session=False)
    deleted += db.query(WebDailyUsage).filter(WebDailyUsage.day < cutoff_day).delete(synchronize_session=False)
    deleted += db.query(AgentDailyUsage).filter(AgentDailyUsage.day < cutoff_day).delete(synchronize_session=False)
    deleted += db.query(DailyTimeAdjustment).filter(DailyTimeAdjustment.day < cutoff_day).delete(synchronize_session=False)
    db.commit()
    return deleted


@router.delete("/events/cleanup-old-records")
def cleanup_old_events(principal: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    return {"status": "success", "deleted_records_count": purge_older_than(db)}


@router.delete("/data/purge-child/{child_id}")
async def purge_child_data(child_id: int, request: Request, principal: Principal = Depends(require_parent),
                           db: Session = Depends(get_db)):
    """Quyền được xóa: xóa toàn bộ dữ liệu hoạt động của trẻ trên máy chủ và bộ nhớ đệm của Agent."""
    child = authorize_child(db, principal, child_id)
    counts = {}
    for model in (DeviceEvent, AccessHistoryLog, MonitoringSession, TimeRequest, WebDailyUsage,
                  AgentDailyUsage, DailyTimeAdjustment, AuditLog):
        counts[model.__tablename__] = db.query(model).filter(model.child_id == child.id).delete(synchronize_session=False)
    db.query(ChildWindowLock).filter_by(child_id=child.id).delete()
    audit.record(db, principal, "data_purged", child_id=child.id, ip=client_ip(request), new=counts)
    db.commit()
    await manager.send_to_agents({"cmd": "purge_cache", "child_id": child.id}, child.id)
    return {"status": "success", "deleted": counts,
            "message": f"Đã xóa toàn bộ dữ liệu hoạt động của trẻ và yêu cầu Agent xóa bộ nhớ đệm"}


# ==========================================
# 5. SỐ LIỆU CHO DASHBOARD
# ==========================================
@router.get("/web-usage/{child_id}")
def get_web_usage(child_id: int, principal: Principal = Depends(require_parent), db: Session = Depends(get_db)):
    child = authorize_child(db, principal, child_id)
    return time_snapshot(child.id, datetime.now().date(), db)


@router.get("/dashboard-stats/{child_id}")
def get_dashboard_stats(child_id: int, principal: Principal = Depends(require_parent), db: Session = Depends(get_db)):
    child = authorize_child(db, principal, child_id)
    today = datetime.now().date()
    snapshot = time_snapshot(child.id, today, db)
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    return {
        **snapshot,
        "weekly_labels": [day.strftime("%d/%m") for day in days],
        "weekly_usage": [daily_usage_seconds(child.id, day, db) // 60 for day in days[:-1]] + [snapshot["today_minutes"]],
    }

