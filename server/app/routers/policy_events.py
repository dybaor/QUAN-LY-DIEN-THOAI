import hashlib
from sqlalchemy import case, func
from sqlalchemy.dialects.sqlite import insert
from datetime import date, datetime, timedelta
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
try:
    from pydantic import BaseModel, Field, field_validator
except ImportError:
    from pydantic import BaseModel, Field, validator as field_validator
from sqlalchemy.orm import Session

from ..database import get_db
from ..daily_time import adjust_today, adjustment_minutes
from ..models import DeviceEvent, Policy, Child, MonitoringSession, AccessHistoryLog, WebDailyUsage, DailyTimeAdjustment, ChildWindowLock, TimeRequest
from ..websocket_manager import manager

router = APIRouter(tags=["Policies & Events"])


# ==========================================
# PYDANTIC SCHEMAS
# ==========================================
class DeductTimeSchema(BaseModel):
    child_id: int = 1
    deduct_min: int = Field(default=15, ge=1, le=480, description="Số phút cần trừ bớt")
    reason: str = Field(default="Phụ huynh phạt trừ bớt thời gian giải trí", max_length=255)


class PolicyUpdateSchema(BaseModel):
    child_id: int
    daily_quota_weekday_min: int = Field(ge=0, le=1440, description="Phút ngày thường")
    daily_quota_weekend_min: int = Field(ge=0, le=1440, description="Phút cuối tuần")
    schedule_matrix: Optional[str] = "1" * 168
    blocked_apps: Optional[str] = ""
    blocked_domains: Optional[str] = ""
    child_name: Optional[str] = None
    lock_pin: Optional[str] = None

    @field_validator("schedule_matrix")
    @classmethod
    def validate_schedule_matrix(cls, v):
        if v is not None:
            v = v.strip()
            # Hỗ trợ chuẩn mới 168 ký tự (7 ngày x 24 giờ) và tương thích chuẩn cũ 336 ký tự
            if len(v) not in (168, 336):
                raise ValueError("Ma trận lịch tuần schedule_matrix bắt buộc phải có đúng 168 ký tự (7 ngày x 24 khung giờ)")
            if not all(c in ("0", "1") for c in v):
                raise ValueError("Ma trận lịch tuần chỉ được chứa các ký tự '0' (khóa) hoặc '1' (cho phép)")
        return v


class SettingsUpdateSchema(BaseModel):
    child_id: int = 1
    child_name: str = Field(default="", max_length=100, description="Tên của trẻ")
    lock_pin: str = Field(..., min_length=4, max_length=50, description="Mật khẩu hoặc mã PIN mở khóa do phụ huynh cài đặt")


class VerifyPinSchema(BaseModel):
    unlock_window: bool = False
    child_id: Optional[int] = 1
    pin: Optional[str] = None
    password: Optional[str] = None
    lock_pin: Optional[str] = None


class LaunchAppSchema(BaseModel):
    app_id: str = Field(..., description="Mã ứng dụng muốn mở: calc, notepad, paint, wordpad")


class EventCreateSchema(BaseModel):
    ts: datetime
    device_id: str
    child_id: int
    type: str
    subject: str
    duration_sec: int
    policy_id: Optional[int] = None


class MonitoringStartSchema(BaseModel):
    child_id: int = 1
    device_id: str = "CHILD-PC"


class MonitoringStopSchema(BaseModel):
    session_id: Optional[int] = None
    child_id: int = 1


class AccessLogCreateSchema(BaseModel):
    child_id: int = 1
    device_id: str = "CHILD-PC"
    target_name: str
    target_type: str = "Trang web"  # "Ứng dụng", "Trang web", "Tìm kiếm"
    status: str = "allowed"  # "allowed", "blocked"



# ==========================================
# 1. API QUẢN LÝ CHÍNH SÁCH (POLICY)
# ==========================================
@router.get("/policy/{child_id}")
def get_child_policy(child_id: int, db: Session = Depends(get_db)):
    """Lấy chính sách hiện tại của trẻ, tạo mặc định nếu chưa tồn tại."""
    policy = db.query(Policy).filter(Policy.child_id == child_id).first()
    if not policy:
        policy = Policy(child_id=child_id)
        db.add(policy)
        db.commit()
        db.refresh(policy)
    day = datetime.now().date()
    policy.adjustment_date = day.isoformat()
    policy.adjustment_minutes = adjustment_minutes(db, child_id, day)
    return policy


@router.put("/policy/update")
async def update_policy(req: PolicyUpdateSchema, db: Session = Depends(get_db)):
    """Cập nhật chính sách, tăng version và phát thông báo WebSocket tức thì cho Agent."""
    policy = db.query(Policy).filter(Policy.child_id == req.child_id).first()
    if not policy:
        policy = Policy(child_id=req.child_id)
        db.add(policy)

    policy.daily_quota_weekday_min = req.daily_quota_weekday_min
    policy.daily_quota_weekend_min = req.daily_quota_weekend_min
    if req.schedule_matrix:
        policy.schedule_matrix = req.schedule_matrix
    if req.blocked_apps is not None:
        policy.blocked_apps = req.blocked_apps
    if req.blocked_domains is not None:
        policy.blocked_domains = req.blocked_domains
    if req.child_name is not None:
        policy.child_name = req.child_name.strip()
    if req.lock_pin is not None:
        policy.lock_pin = req.lock_pin.strip()
    policy.version += 1
    policy.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(policy)

    # Bắn tín hiệu WebSocket thông báo Agent đồng bộ ngay lập tức (< 1s)
    await manager.broadcast({
        "cmd": "sync_policy",
        "child_id": policy.child_id,
        "version": policy.version,
        "child_name": policy.child_name,
        "lock_pin": policy.lock_pin
    })

    return {
        "status": "success", 
        "policy_version": policy.version,
        "child_name": policy.child_name,
        "lock_pin": policy.lock_pin
    }


# ==========================================
# 1.1 API CẤU HÌNH THÔNG TIN BÉ & MÃ PIN KHÓA MÁY
# ==========================================
@router.post("/api/settings/initialize")
@router.post("/api/settings/update")
@router.post("/api/auth/setup")
@router.post("/api/auth/initialize")
def update_settings(req: SettingsUpdateSchema, background_tasks: BackgroundTasks = None, db: Session = Depends(get_db)):
    """Cập nhật / Khởi tạo Tên bé và Mã PIN khóa máy từ Dashboard Phụ huynh, đồng bộ tức thì qua WebSocket."""
    policy = db.query(Policy).filter(Policy.child_id == req.child_id).first()
    if not policy:
        policy = Policy(child_id=req.child_id)
        db.add(policy)

    new_name = req.child_name.strip()
    new_pin = req.lock_pin.strip()

    if not new_name:
        raise HTTPException(status_code=400, detail="Vui lòng nhập tên của trẻ")
    if not new_pin or len(new_pin) < 4 or len(new_pin) > 6:
        raise HTTPException(status_code=400, detail="Mã PIN quản lý phải có độ dài từ 4 đến 6 chữ số")

    policy.child_name = new_name
    policy.lock_pin = new_pin
    policy.lock_password_hash = hashlib.sha256(new_pin.encode("utf-8")).hexdigest()
    policy.version += 1
    policy.updated_at = datetime.utcnow()

    # Đồng bộ sang bảng Child nếu tồn tại
    child = db.query(Child).filter(Child.id == req.child_id).first()
    if child:
        child.name = new_name

    db.commit()
    db.refresh(policy)

    # Phát tín hiệu WebSocket cho cả Dashboard phụ huynh và Cửa sổ trẻ em trong Background
    if background_tasks:
        background_tasks.add_task(manager.broadcast, {
            "cmd": "init_completed",
            "child_id": policy.child_id,
            "child_name": policy.child_name,
            "lock_pin": policy.lock_pin,
            "version": policy.version
        })
        background_tasks.add_task(manager.broadcast, {
            "cmd": "settings_updated",
            "child_id": policy.child_id,
            "child_name": policy.child_name,
            "lock_pin": policy.lock_pin,
            "version": policy.version
        })

    return {
        "status": "success",
        "success": True,
        "child_id": policy.child_id,
        "child_name": policy.child_name,
        "lock_pin": policy.lock_pin,
        "version": policy.version,
        "is_initialized": True,
        "is_configured": True,
        "message": f"Đã lưu thành công thông tin bé '{policy.child_name}' và mã PIN bảo vệ."
    }


@router.get("/api/auth/status")
@router.get("/api/auth/status/{child_id}")
@router.get("/api/settings/{child_id}")
def get_auth_settings(child_id: int = 1, db: Session = Depends(get_db)):
    """Kiểm tra trạng thái xác thực: Phân biệt rạch ròi Trường hợp A (Hệ thống mới) và Trường hợp B (Đã có PIN)."""
    policy = db.query(Policy).filter(Policy.child_id == child_id).first()
    child_name = (policy.child_name or "").strip() if policy and policy.child_name else ""
    lock_pin = (policy.lock_pin or "").strip() if policy and policy.lock_pin else ""
    lock_hash = (policy.lock_password_hash or "").strip() if policy and policy.lock_password_hash else ""
    
    # RẠCH RÒI 2 TRƯỜNG HỢP:
    # Trường hợp A: Hệ thống mới nếu chưa có Tên bé HOẶC chưa có Mã PIN
    # Trường hợp B: Hệ thống đã có tên bé VÀ có mã PIN (plain hoặc hash)
    has_pin = bool(lock_pin or lock_hash)
    is_initialized = bool(child_name and has_pin)
    
    # Kiểm tra xem có kết nối phụ huynh đang trực tuyến không
    parent_online = any(str(k).startswith("parent_") for k in manager.active_connections.keys())
    
    return {
        "status": "success",
        "success": True,
        "child_id": child_id,
        "child_name": child_name,
        "lock_pin": lock_pin,
        "has_pin": has_pin,
        "is_initialized": is_initialized,
        "is_configured": is_initialized,
        "parent_authenticated": parent_online
    }

get_settings = get_auth_settings


@router.post("/api/system/reset")
def reset_system_state(db: Session = Depends(get_db)):
    """Reset trạng thái hệ thống về Trường hợp A (sạch) để kiểm thử luồng khởi tạo ban đầu."""
    policy = db.query(Policy).filter(Policy.child_id == 1).first()
    if policy:
        policy.child_name = None
        policy.lock_pin = None
        policy.lock_password_hash = None
        policy.daily_quota_weekday_min = 120
        policy.daily_quota_weekend_min = 180
        policy.schedule_matrix = "1" * 168
        policy.blocked_apps = ""
        policy.blocked_domains = ""
        policy.version = 1
    child = db.query(Child).filter(Child.id == 1).first()
    if child:
        child.name = None
    db.query(ChildWindowLock).delete()
    db.query(DailyTimeAdjustment).delete()
    db.query(TimeRequest).delete()
    db.query(WebDailyUsage).delete()
    db.query(DeviceEvent).delete()
    db.query(MonitoringSession).delete()
    db.query(AccessHistoryLog).delete()
    db.commit()
    return {
        "status": "success",
        "success": True,
        "message": "Đã reset hệ thống về trạng thái sạch (Trường hợp A: Chưa có Tên bé và chưa có Mã PIN)"
    }


@router.post("/api/auth/verify-pin")
@router.post("/api/auth/login")
@router.post("/api/settings/verify-pin")
def verify_pin(req: VerifyPinSchema, db: Session = Depends(get_db)):
    """Xác thực mã PIN mở khóa:
    - So khớp trực tiếp plain text nếu lưu thô
    - So khớp hàm băm SHA-256 nếu lưu mã băm
    - Trả về chuẩn xác {"success": True, "message": "...", "child_name": ...}
    """
    child_id = req.child_id or 1
    policy = db.query(Policy).filter(Policy.child_id == child_id).first()
    saved_pin = str(policy.lock_pin or "").strip() if policy and policy.lock_pin else ""
    saved_hash = str(policy.lock_password_hash or "").strip() if policy and policy.lock_password_hash else ""

    if not policy or not (saved_pin or saved_hash):
        return {
            "success": False,
            "status": "failed",
            "valid": False,
            "verified": False,
            "message": "Chưa có mã PIN phụ huynh nào được thiết lập!",
            "child_name": ""
        }

    input_pin = (req.pin or req.password or req.lock_pin or "").strip()
    if not input_pin:
        return {
            "success": False,
            "status": "failed",
            "valid": False,
            "verified": False,
            "message": "Vui lòng nhập mã PIN bảo mật!",
            "child_name": policy.child_name or ""
        }

    input_hash = hashlib.sha256(input_pin.encode("utf-8")).hexdigest()

    # 1. So khớp plain text
    is_valid = False
    if saved_pin and input_pin == saved_pin:
        is_valid = True
    # 2. So khớp hash SHA-256
    elif saved_hash and input_hash == saved_hash:
        is_valid = True
    elif saved_pin and input_hash == saved_pin:
        is_valid = True

    if is_valid and req.unlock_window:
        db.query(ChildWindowLock).filter_by(child_id=child_id).delete()
        db.commit()

    if is_valid:
        # Bắn WebSocket init_completed cho tất cả cửa sổ trẻ em tự động mở
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            loop.create_task(manager.broadcast({
                "cmd": "init_completed",
                "child_id": child_id,
                "child_name": policy.child_name or "",
                "lock_pin": policy.lock_pin or "",
                "version": policy.version
            }))
        except Exception:
            pass

    return {
        "success": is_valid,
        "status": "success" if is_valid else "failed",
        "valid": is_valid,
        "verified": is_valid,
        "message": "Xác thực thành công" if is_valid else "Mã PIN không chính xác. Vui lòng thử lại!",
        "child_name": policy.child_name or ""
    }


# ==========================================
# 1.2 API LỊCH SỬ QUAN SÁT MÀN HÌNH (MONITORING SESSIONS)
# ==========================================
@router.post("/api/monitoring/start")
def start_monitoring_session(req: MonitoringStartSchema, db: Session = Depends(get_db)):
    """Bắt đầu phiên theo dõi màn hình trẻ."""
    session = MonitoringSession(
        child_id=req.child_id,
        device_id=req.device_id,
        start_time=datetime.utcnow(),
        status="Đang theo dõi"
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return {
        "status": "success",
        "session_id": session.id,
        "start_time": session.start_time.strftime("%H:%M:%S %d/%m/%Y")
    }


@router.post("/api/monitoring/stop")
def stop_monitoring_session(req: MonitoringStopSchema, db: Session = Depends(get_db)):
    """Kết thúc phiên theo dõi màn hình trẻ."""
    query = db.query(MonitoringSession).filter(MonitoringSession.child_id == req.child_id)
    if req.session_id:
        session = query.filter(MonitoringSession.id == req.session_id).first()
    else:
        session = query.filter(MonitoringSession.status == "Đang theo dõi").order_by(MonitoringSession.start_time.desc()).first()

    now = datetime.utcnow()
    duration = 0
    if session:
        session.end_time = now
        duration = max(0, int((now - session.start_time).total_seconds()))
        session.duration_sec = duration
        session.status = "Đã kết thúc"
        db.commit()
        db.refresh(session)
        return {
            "status": "success",
            "session_id": session.id,
            "duration_sec": duration,
            "end_time": session.end_time.strftime("%H:%M:%S %d/%m/%Y")
        }

    return {"status": "success", "duration_sec": 0, "message": "Không tìm thấy phiên cần đóng"}


@router.get("/api/monitoring/history/{child_id}")
def get_monitoring_history(child_id: int, limit: int = 30, db: Session = Depends(get_db)):
    """Lấy danh sách các phiên quan sát màn hình."""
    sessions = (
        db.query(MonitoringSession)
        .filter(MonitoringSession.child_id == child_id)
        .order_by(MonitoringSession.start_time.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": s.id,
            "start_time": s.start_time.strftime("%H:%M:%S %d/%m/%Y"),
            "end_time": s.end_time.strftime("%H:%M:%S %d/%m/%Y") if s.end_time else "-",
            "duration": f"{s.duration_sec} giây" if s.duration_sec else ("Đang theo dõi" if s.status == "Đang theo dõi" else "-"),
            "status": s.status
        }
        for s in sessions
    ]


# ==========================================
# 1.3 API NHẬT KÝ TRUY CẬP THIẾT BỊ (ACCESS HISTORY LOG)
# ==========================================
@router.post("/api/access-log")
def create_access_log(req: AccessLogCreateSchema, db: Session = Depends(get_db)):
    """Ghi nhận lịch sử truy cập ứng dụng/web của trẻ."""
    log = AccessHistoryLog(
        child_id=req.child_id,
        device_id=req.device_id,
        ts=datetime.utcnow(),
        target_name=req.target_name.strip(),
        target_type=req.target_type.strip(),
        status=req.status.strip()
    )
    db.add(log)

    # Ghi đồng thời vào DeviceEvent để tương thích kiểm toán 7 trường
    ev_type = "app_start" if req.target_type == "Ứng dụng" and req.status == "allowed" else (
        "blocked_app" if req.target_type == "Ứng dụng" else (
            "web_visit" if req.status == "allowed" else "blocked_domain"
        )
    )
    db.add(DeviceEvent(
        ts=log.ts,
        device_id=req.device_id,
        child_id=req.child_id,
        type=ev_type,
        subject=req.target_name,
        duration_sec=0
    ))

    db.commit()
    db.refresh(log)
    return {"status": "success", "id": log.id}


@router.get("/api/access-history/{child_id}")
def get_access_history(child_id: int, limit: int = 30, db: Session = Depends(get_db)):
    """Lấy danh sách lịch sử truy cập thiết bị của trẻ."""
    logs = (
        db.query(AccessHistoryLog)
        .filter(AccessHistoryLog.child_id == child_id)
        .order_by(AccessHistoryLog.ts.desc())
        .limit(limit)
        .all()
    )
    if logs:
        return [
            {
                "id": l.id,
                "ts": l.ts.strftime("%H:%M:%S %d/%m/%Y"),
                "target_name": l.target_name,
                "target_type": l.target_type,
                "status": l.status,
                "status_label": "✅ Hợp lệ" if l.status == "allowed" else "⛔ Bị chặn"
            }
            for l in logs
        ]

    # Fallback từ DeviceEvent nếu AccessHistoryLog chưa có bản ghi nào
    events = (
        db.query(DeviceEvent)
        .filter(
            DeviceEvent.child_id == child_id,
            DeviceEvent.type.in_(("app_start", "blocked_app", "web_visit", "blocked_domain", "query_filter", "blocked_keyword"))
        )
        .order_by(DeviceEvent.ts.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": e.id,
            "ts": e.ts.strftime("%H:%M:%S %d/%m/%Y"),
            "target_name": e.subject,
            "target_type": "Ứng dụng" if "app" in e.type else "Trang web",
            "status": "blocked" if "block" in e.type or "filter" in e.type else "allowed",
            "status_label": "⛔ Bị chặn" if ("block" in e.type or "filter" in e.type) else "✅ Hợp lệ"
        }
        for e in events
    ]



@router.post("/agent/launch-app")
def launch_desktop_app(req: LaunchAppSchema):
    """Mô phỏng mở ứng dụng an toàn cho trẻ - Tuyệt đối không can thiệp hay khởi chạy phần mềm thật ngoài Windows OS."""
    app_whitelist = {
        "calc": "Máy tính Casio",
        "calculator": "Máy tính Casio",
        "notepad": "Sổ tay Ghi chú",
        "paint": "MS Paint Vẽ hình",
        "mspaint": "MS Paint Vẽ hình",
        "wordpad": "WordPad Soạn thảo",
        "write": "WordPad Soạn thảo",
        "osk": "Bàn phím ảo",
    }
    
    app_key = req.app_id.strip().lower()
    if app_key not in app_whitelist:
        raise HTTPException(status_code=400, detail=f"Ứng dụng '{req.app_id}' không nằm trong danh mục được phép mở an toàn.")
    
    return {
        "status": "success",
        "app_id": app_key,
        "app_name": app_whitelist[app_key],
        "message": f"Đang mô phỏng ứng dụng {app_whitelist[app_key]}"
    }


@router.post("/policy/deduct-time")
async def deduct_child_time(req: DeductTimeSchema, db: Session = Depends(get_db)):
    """Trừ bớt thời gian giải trí thời gian thực từ phía Phụ huynh."""
    policy = db.query(Policy).filter(Policy.child_id == req.child_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Không tìm thấy chính sách của trẻ")
    remaining = time_snapshot(req.child_id, datetime.now().date(), db)["remaining_seconds"]
    deducted = min(req.deduct_min, (remaining + 59) // 60)
    if deducted:
        adjust_today(db, req.child_id, -deducted)
    db.commit()
    db.refresh(policy)

    # Phát thông báo WebSocket time_deducted thời gian thực xuống máy con
    await manager.broadcast({
        "cmd": "time_deducted",
        "child_id": req.child_id,
        "deduct_min": deducted,
        "reason": req.reason,
        "adjustment_date": datetime.now().date().isoformat()
    })

    return {
        "status": "success",
        "deducted_minutes": deducted,
        "daily_quota_weekday_min": policy.daily_quota_weekday_min,
        "daily_quota_weekend_min": policy.daily_quota_weekend_min,
        "policy_version": policy.version,
        "message": f"Đã giảm {deducted} phút của trẻ thành công"
    }


# ==========================================
# 2. API TIẾP NHẬN SỰ KIỆN (EVENTS - 7 TRƯỜNG)
# ==========================================
@router.post("/events/", status_code=status.HTTP_201_CREATED)
def receive_event_single(event_data: Union[EventCreateSchema, List[EventCreateSchema]], db: Session = Depends(get_db)):
    """Tiếp nhận một hoặc nhiều sự kiện từ Agent theo chuẩn 7 trường."""
    if isinstance(event_data, list):
        items = event_data
    else:
        items = [event_data]

    new_events = [
        DeviceEvent(
            ts=ev.ts,
            device_id=ev.device_id,
            child_id=ev.child_id,
            type=ev.type,
            subject=ev.subject,
            duration_sec=ev.duration_sec,
            policy_id=ev.policy_id,
        )
        for ev in items
    ]
    db.add_all(new_events)
    db.commit()

    # Bắn thông báo Toast thời gian thực lên Web UI (100% Zero-OS Popup)
    import asyncio
    for ev in items:
        if ev.type in ("blocked_app", "blocked_domain", "blocked_keyword", "query_filter", "clock_tamper", "locked"):
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(manager.broadcast({
                        "cmd": "violation_toast",
                        "type": ev.type,
                        "subject": ev.subject,
                        "message": f"Phát hiện chặn: {ev.subject} ({ev.type})"
                    }))
            except Exception:
                pass

    return {"status": "success", "recorded_count": len(new_events)}


@router.post("/events/batch", status_code=status.HTTP_201_CREATED)
def receive_events_batch(events: List[EventCreateSchema], db: Session = Depends(get_db)):
    """Tiếp nhận sự kiện theo lô từ máy con Agent (kể cả khi vừa kết nối mạng lại)."""
    return receive_event_single(events, db)


@router.get("/events/violations/{child_id}")
def get_violation_events(child_id: int, limit: int = 50, db: Session = Depends(get_db)):
    """Lấy danh sách các sự kiện vi phạm mới nhất phục vụ Bảng nhật ký thời gian thực."""
    violation_types = [
        "blocked_app",
        "blocked_domain",
        "blocked_keyword",
        "query_filter",
        "clock_tamper",
        "locked",
        "quota_exceeded"
    ]
    events = (
        db.query(DeviceEvent)
        .filter(DeviceEvent.child_id == child_id, DeviceEvent.type.in_(violation_types))
        .order_by(DeviceEvent.ts.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": e.id,
            "ts": e.ts.strftime("%H:%M:%S %d/%m/%Y"),
            "device_id": e.device_id,
            "type": e.type,
            "subject": e.subject,
            "duration_sec": e.duration_sec,
            "action": (
                "Đã dừng tiến trình" if e.type == "blocked_app"
                else (
                    "Chặn từ khóa cấm" if e.type in ("blocked_keyword", "query_filter")
                    else ("Đã khóa máy" if e.type in ("locked", "quota_exceeded") else "Sinkhole 0.0.0.0")
                )
            )
        }
        for e in events
    ]


@router.get("/events/summary/{child_id}")
def get_usage_summary(child_id: int, db: Session = Depends(get_db)):
    """Tổng hợp sơ bộ thời gian sử dụng phục vụ kiểm toán."""
    events = db.query(DeviceEvent).filter(DeviceEvent.child_id == child_id).all()
    total_seconds = sum(e.duration_sec for e in events)
    return {
        "child_id": child_id,
        "total_usage_minutes": round(total_seconds / 60, 1),
        "total_events_logged": len(events),
    }


# ==========================================
# 3. QUẢN TRỊ DỮ LIỆU & QUYỀN RIÊNG TƯ (NĐ 13/2023)
# ==========================================
@router.delete("/events/cleanup-old-records")
def cleanup_old_events(db: Session = Depends(get_db)):
    """Xóa tự động các sự kiện cũ hơn 90 ngày theo hạn mức lưu trữ F3."""
    cutoff_date = datetime.utcnow() - timedelta(days=90)
    deleted_rows = db.query(DeviceEvent).filter(DeviceEvent.ts < cutoff_date).delete()
    db.query(WebDailyUsage).filter(WebDailyUsage.day < (datetime.now().date() - timedelta(days=90))).delete()
    db.query(DailyTimeAdjustment).filter(DailyTimeAdjustment.day < cutoff_date.date()).delete()
    db.commit()
    return {"status": "success", "deleted_records_count": deleted_rows}


@router.delete("/data/purge-child/{child_id}")
def purge_child_data(child_id: int, db: Session = Depends(get_db)):
    """Quyền được quên (Right to be Forgotten): Xóa toàn bộ dữ liệu của một trẻ."""
    del_events = db.query(DeviceEvent).filter(DeviceEvent.child_id == child_id).delete()
    db.query(WebDailyUsage).filter(WebDailyUsage.child_id == child_id).delete()
    db.query(DailyTimeAdjustment).filter(DailyTimeAdjustment.child_id == child_id).delete()
    db.query(ChildWindowLock).filter_by(child_id=child_id).delete()
    del_policies = db.query(Policy).filter(Policy.child_id == child_id).delete()
    db.commit()
    return {
        "status": "success",
        "message": f"Đã xóa vĩnh viễn toàn bộ dữ liệu liên quan đến trẻ ID {child_id}",
        "events_deleted": del_events,
        "policies_deleted": del_policies,
    }


# ==========================================
# 4. SỐ LIỆU ĐỘNG CHO WEB DASHBOARD
# ==========================================
def daily_usage_seconds(child_id: int, day: date, db: Session) -> int:
    start = datetime.combine(day, datetime.min.time())
    end = start + timedelta(days=1)
    # Agent timestamps are stored as naive UTC; day boundaries use server local time.
    start_utc = datetime.utcfromtimestamp(start.timestamp())
    end_utc = datetime.utcfromtimestamp(end.timestamp())
    agent_seconds = db.query(func.sum(DeviceEvent.duration_sec)).filter(
        DeviceEvent.child_id == child_id, DeviceEvent.type == "app_stop",
        DeviceEvent.ts >= start_utc, DeviceEvent.ts < end_utc,
    ).scalar() or 0
    web = db.get(WebDailyUsage, (child_id, day))
    # Both sources can observe the same activity, so avoid adding overlapping usage.
    return max(0, agent_seconds, int(web.used_seconds) if web else 0)


def time_snapshot(child_id: int, day: date, db: Session) -> dict:
    policy = db.query(Policy).filter(Policy.child_id == child_id).first()
    quota = 90
    if policy:
        quota = policy.daily_quota_weekend_min if day.weekday() >= 5 else policy.daily_quota_weekday_min
    adjustment = adjustment_minutes(db, child_id, day)
    effective_quota = max(0, quota + adjustment)
    used = daily_usage_seconds(child_id, day, db)
    lock = db.get(ChildWindowLock, child_id)
    return {
        "lock_reason": lock.reason if lock else None,
        "today_minutes": used // 60,
        "today_seconds": used,
        "quota_minutes": effective_quota,
        "base_quota_minutes": quota,
        "adjustment_minutes": adjustment,
        "remaining_seconds": max(0, effective_quota * 60 - used),
    }


@router.post("/web-usage/{child_id}")
def track_web_usage(child_id: int, db: Session = Depends(get_db)):
    now = datetime.now()
    day = now.date()
    settings = get_auth_settings(child_id, db)
    snapshot = time_snapshot(child_id, day, db)
    if settings["is_initialized"] and not snapshot["lock_reason"] and snapshot["remaining_seconds"] > 0:
        sample = insert(WebDailyUsage).values(
            child_id=child_id, day=day, used_seconds=0, last_seen=now.timestamp(),
        )
        gap = sample.excluded.last_seen - WebDailyUsage.last_seen
        db.execute(sample.on_conflict_do_update(
            index_elements=[WebDailyUsage.child_id, WebDailyUsage.day],
            set_={
                "used_seconds": WebDailyUsage.used_seconds + case(
                    (gap.between(0, 12), gap), else_=0,
                ),
                "last_seen": func.max(WebDailyUsage.last_seen, sample.excluded.last_seen),
            },
        ))
        db.commit()
    return time_snapshot(child_id, day, db)


@router.get("/web-usage/{child_id}")
def get_web_usage(child_id: int, db: Session = Depends(get_db)):
    return time_snapshot(child_id, datetime.now().date(), db)


@router.get("/dashboard-stats/{child_id}")
def get_dashboard_stats(child_id: int, db: Session = Depends(get_db)):
    today = datetime.now().date()
    snapshot = time_snapshot(child_id, today, db)
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    return {
        **snapshot,
        "weekly_labels": [day.strftime("%d/%m") for day in days],
        "weekly_usage": [
            daily_usage_seconds(child_id, day, db) // 60 for day in days[:-1]
        ] + [snapshot["today_minutes"]],
    }
