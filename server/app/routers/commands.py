import json
import time
from datetime import date, datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from .. import audit, config
from ..daily_time import adjust_today
from ..database import SessionLocal, get_db
from ..deps import (
    Principal, authorize_child, client_ip, owned_child_ids, require_device, require_parent, websocket_principal,
)
from ..models import ROLE_ADMIN, ROLE_CHILD, ROLE_DEVICE, ROLE_PARENT, AgentDailyUsage, ChildWindowLock, Device, Policy
from ..services import get_or_create_policy, signed_policy
from ..websocket_manager import manager
from .policy_events import add_event

router = APIRouter(tags=["Commands & WebSocket"])

# Trạng thái đồng thuận xem màn hình mới nhất theo từng trẻ
consent_status = {}
LOCK_ACTIONS = ("lock", "lock_now", "lock_window")
UNLOCK_ACTIONS = ("unlock", "unlock_window")


def set_consent(child_id: int, state: str, message: str):
    consent_status[child_id] = {"feature": "screen", "status": state, "message": message,
                                "timestamp": datetime.utcnow().isoformat() + "Z"}


class CommandRequest(BaseModel):
    child_id: int = Field(..., ge=1)
    action: str  # lock_window, unlock_window, close_session, extend_time, request_screen_consent
    device_id: Optional[str] = None
    duration_min: Optional[int] = 0
    reason: str = Field(default="Lệnh từ phụ huynh", max_length=255)


class HeartbeatRequest(BaseModel):
    status: str = "online"
    current_policy_version: Optional[int] = 1
    usage_day: Optional[date] = None
    quota_used: Optional[int] = Field(default=None, ge=0, le=86400, description="Số giây đã dùng trong ngày")
    used_seconds: Optional[int] = Field(default=None, ge=0, le=86400, description="Tên cũ của quota_used")
    client_time: Optional[float] = None
    ui_present: bool = True


def save_window_lock(db: Session, child_id: int, reason: Optional[str]):
    if reason is None:
        db.query(ChildWindowLock).filter_by(child_id=child_id).delete()
    else:
        lock = insert(ChildWindowLock).values(child_id=child_id, reason=reason.strip()[:255] or "Lệnh từ phụ huynh")
        db.execute(lock.on_conflict_do_update(index_elements=[ChildWindowLock.child_id],
                                              set_={"reason": lock.excluded.reason}))


async def apply_window_lock(db: Session, principal: Principal, child_id: int, lock: bool, reason: str, ip: str):
    save_window_lock(db, child_id, reason if lock else None)
    if lock:
        add_event(db, child_id, "parent-dashboard", "locked", reason)
    else:
        add_event(db, child_id, "parent-dashboard", "override_granted", "Phụ huynh mở khóa máy")
    audit.record(db, principal, "window_locked" if lock else "window_unlocked", child_id=child_id, ip=ip,
                 new={"reason": reason} if lock else None)
    db.commit()
    await manager.notify_child({"cmd": "lock_window" if lock else "unlock_window", "child_id": child_id,
                                "reason": reason if lock else None}, child_id)


# ---------- 1. Heartbeat & chính sách có chữ ký cho Agent ----------
@router.post("/heartbeat")
async def receive_heartbeat(req: HeartbeatRequest, request: Request, principal: Principal = Depends(require_device),
                            db: Session = Depends(get_db)):
    """Agent gọi mỗi 60 giây: báo hạn mức đã dùng, nhận giờ máy chủ để đối chiếu chống chỉnh đồng hồ."""
    device = db.get(Device, principal.device_id)
    policy = get_or_create_policy(db, device.child)
    used = req.quota_used if req.quota_used is not None else req.used_seconds
    if req.usage_day == datetime.now().date() and used is not None:
        usage = insert(AgentDailyUsage).values(child_id=device.child_id, day=req.usage_day, device_id=device.id,
                                               used_seconds=used)
        db.execute(usage.on_conflict_do_update(
            index_elements=[AgentDailyUsage.child_id, AgentDailyUsage.day, AgentDailyUsage.device_id],
            set_={"used_seconds": func.max(AgentDailyUsage.used_seconds, usage.excluded.used_seconds)},
        ))
    if bool(device.ui_present) != req.ui_present:
        device.ui_present = req.ui_present
        audit.record(db, principal, "agent_ui_restored" if req.ui_present else "agent_ui_missing",
                     child_id=device.child_id, ip=client_ip(request))
        await manager.send_to_parents({"cmd": "device_status", "child_id": device.child_id, "device_id": device.id,
                                       "ui_present": req.ui_present}, device.child_id)
    device.last_seen = datetime.utcnow()
    db.commit()
    return {
        "status": "ack",
        "server_time": datetime.utcnow().isoformat() + "Z",
        "server_epoch": time.time(),
        "need_policy_update": policy.version > (req.current_policy_version or 0),
        "latest_version": policy.version,
        "heartbeat_interval": config.HEARTBEAT_INTERVAL_SEC,
    }


@router.get("/agent/policy")
def get_signed_policy(principal: Principal = Depends(require_device), db: Session = Depends(get_db)):
    """Chính sách kèm chữ ký HMAC-SHA256 bằng khóa riêng của thiết bị (F4-2)."""
    device = db.get(Device, principal.device_id)
    policy = get_or_create_policy(db, device.child)
    return signed_policy(db, policy, device.id, device.policy_key)


# ---------- 2. WebSocket ----------
def chat_payload(obj: dict, sender: str) -> dict:
    return {
        "cmd": "chat_message",
        "message_id": str(obj.get("message_id") or uuid4().hex)[:64],
        "sender": sender,
        "text": str(obj.get("text", ""))[:1000],
        "timestamp": obj.get("timestamp") or datetime.now().strftime("%H:%M:%S %d/%m/%Y"),
    }


@router.websocket("/ws/parent")
async def parent_websocket(websocket: WebSocket):
    with SessionLocal() as db:
        principal = websocket_principal(db, websocket, {ROLE_PARENT, ROLE_ADMIN})
        scope = owned_child_ids(db, principal) if principal else []
    if not principal:
        await websocket.close(code=4401)
        return
    key = f"parent_{principal.parent_id}_{uuid4().hex[:8]}"
    await manager.connect(key, websocket, scope)
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if not message.get("text"):
                continue
            try:
                obj = json.loads(message["text"])
                child_id = int(obj.get("child_id") or 0)
            except (ValueError, TypeError):
                continue
            if child_id not in manager.scopes.get(key, set()):
                continue
            action = obj.get("action") or obj.get("cmd") or obj.get("type")
            if action in ("chat_message", "chat"):
                payload = {**chat_payload(obj, "parent"), "child_id": child_id}
                await manager.send_to_children(payload, child_id)
                await manager.send_to_parents(payload, child_id)
            elif action in ("request_screen", "request_screen_consent"):
                set_consent(child_id, "pending", "Đang gửi yêu cầu đồng thuận tới máy của bé...")
                await manager.send_to_children({"cmd": "request_screen_consent", "child_id": child_id,
                                                "reason": str(obj.get("reason") or "Ba mẹ muốn xem màn hình học tập của con")[:255]}, child_id)
            elif action == "stop_screen_share":
                await manager.send_to_children({"cmd": "stop_screen_share", "child_id": child_id}, child_id)
            elif action in LOCK_ACTIONS + UNLOCK_ACTIONS:
                lock = action in LOCK_ACTIONS
                with SessionLocal() as db:
                    await apply_window_lock(db, principal, child_id, lock, str(obj.get("reason") or "Lệnh từ phụ huynh")[:255],
                                            client_ip(websocket))
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(key, websocket)


@router.websocket("/ws/child")
async def child_websocket(websocket: WebSocket):
    """WebSocket của cổng học tập: chỉ trao đổi với phụ huynh sở hữu trẻ."""
    with SessionLocal() as db:
        principal = websocket_principal(db, websocket, {ROLE_CHILD})
    if not principal:
        await websocket.close(code=4401)
        return
    child_id = principal.child_id
    key = f"child_{child_id}_{uuid4().hex[:8]}"
    await manager.connect(key, websocket, [child_id])
    sharing = False
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("bytes"):
                sharing = True
                await manager.send_bytes_to_parents(message["bytes"], child_id)
                continue
            if not message.get("text"):
                continue
            try:
                obj = json.loads(message["text"])
            except ValueError:
                continue
            kind = obj.get("type") or obj.get("action")
            if kind == "consent_response":
                sharing = bool(obj.get("approved"))
                text = "Bé đã ĐỒNG Ý chia sẻ màn hình" if sharing else "Bé đã TỪ CHỐI chia sẻ màn hình"
                set_consent(child_id, "accepted" if sharing else "declined", text)
                await manager.send_to_parents({"cmd": "screen_consent_result", "child_id": child_id,
                                               "approved": sharing, "message": text}, child_id)
            elif kind == "stop_screen_share":
                sharing = False
                set_consent(child_id, "idle", "Đã dừng chia sẻ màn hình")
                await manager.send_to_parents({"cmd": "screen_share_stopped", "child_id": child_id}, child_id)
            elif kind in ("chat_message", "chat"):
                payload = {**chat_payload(obj, "child"), "child_id": child_id}
                await manager.send_to_parents(payload, child_id)
                await manager.send_to_children(payload, child_id)
            elif kind in ("violation_alert", "violation"):
                target = str(obj.get("target_name") or obj.get("target") or "Nội dung hạn chế")[:255]
                ts = obj.get("timestamp") or datetime.now().strftime("%H:%M:%S %d/%m/%Y")
                await manager.send_to_parents({
                    "cmd": "violation_alert", "child_id": child_id, "target_name": target,
                    "target_type": str(obj.get("target_type", "web"))[:50],
                    "violation_type": str(obj.get("violation_type") or "Từ khóa / Tên miền cấm")[:100],
                    "timestamp": ts, "message": f"⚠️ Cảnh báo vi phạm! Bé vừa tìm kiếm/truy cập: {target} vào lúc {ts}",
                }, child_id)
            elif kind in ("time_expired_alert", "time_expired"):
                ts = obj.get("timestamp") or datetime.now().strftime("%H:%M:%S %d/%m/%Y")
                await manager.send_to_parents({"cmd": "time_expired_alert", "child_id": child_id,
                                               "child_name": principal.name or "Bé", "timestamp": ts,
                                               "message": f"Bé {principal.name or ''} đã dùng hết thời gian trong ngày!"}, child_id)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(key, websocket)
        if sharing:
            set_consent(child_id, "idle", "Đã dừng chia sẻ màn hình")
            await manager.send_to_parents({"cmd": "screen_share_stopped", "child_id": child_id}, child_id)


@router.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket):
    """Kênh lệnh khẩn cho Agent (khóa ngay / mở khóa / +giờ ≤ 5 giây). Xác thực bằng Bearer token."""
    with SessionLocal() as db:
        principal = websocket_principal(db, websocket, {ROLE_DEVICE})
    if not principal:
        await websocket.close(code=4401)
        return
    key = f"agent_{principal.device_id}"
    await manager.connect(key, websocket, [principal.child_id])
    await manager.send_to_parents({"cmd": "device_status", "child_id": principal.child_id,
                                   "device_id": principal.device_id, "status": "online"}, principal.child_id)
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if not message.get("text"):
                continue
            try:
                obj = json.loads(message["text"])
            except ValueError:
                continue
            if obj.get("type") in ("quota_warning", "time_expired_alert"):
                await manager.send_to_parents({**obj, "cmd": obj["type"], "child_id": principal.child_id}, principal.child_id)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(key, websocket)
        await manager.send_to_parents({"cmd": "device_status", "child_id": principal.child_id,
                                       "device_id": principal.device_id, "status": "offline"}, principal.child_id)


# ---------- 3. Trạng thái & lệnh từ dashboard ----------
@router.get("/devices/online")
def get_online_devices(child_id: Optional[int] = None, principal: Principal = Depends(require_parent),
                       db: Session = Depends(get_db)):
    ids = [authorize_child(db, principal, child_id).id] if child_id else owned_child_ids(db, principal)
    devices = db.query(Device).filter(Device.child_id.in_(ids), Device.is_active.is_(True)).all() if ids else []
    return {
        "online_devices": [d.id for d in devices if manager.online_keys(f"agent_{d.id}")],
        "portals_online": [cid for cid in ids if manager.online_keys("child_", cid)],
    }


@router.post("/commands/send")
async def send_emergency_command(req: CommandRequest, request: Request, principal: Principal = Depends(require_parent),
                                 db: Session = Depends(get_db)):
    child = authorize_child(db, principal, req.child_id)
    payload = {"cmd": req.action, "id": f"CMD-{uuid4().hex[:12]}", "child_id": child.id, "reason": req.reason,
               "duration_min": req.duration_min}
    if req.action in LOCK_ACTIONS + UNLOCK_ACTIONS:
        await apply_window_lock(db, principal, child.id, req.action in LOCK_ACTIONS, req.reason, client_ip(request))
        return {"status": "success", "command_id": payload["id"], "cmd": req.action}
    if req.action == "extend_time":
        minutes = req.duration_min or 0
        if not 5 <= minutes <= 180:
            raise HTTPException(status_code=422, detail="Thời gian gia hạn phải từ 5 đến 180 phút")
        adjust_today(db, child.id, minutes)
        add_event(db, child.id, "parent-dashboard", "override_granted", f"Cộng thêm {minutes} phút")
        audit.record(db, principal, "time_extended", child_id=child.id, ip=client_ip(request),
                     new={"minutes": minutes, "reason": req.reason})
        db.commit()
        payload["granted_minutes"] = minutes
        await manager.notify_child(payload, child.id)
    elif req.action == "request_screen_consent":
        set_consent(child.id, "pending", "Đang gửi yêu cầu đồng thuận tới máy của bé...")
        await manager.send_to_children(payload, child.id)
    elif req.action in ("close_session", "shutdown_now"):
        # Không đụng Windows: kết thúc phiên = overlay khóa trên Cổng học tập cho tới khi phụ huynh mở khóa
        await apply_window_lock(db, principal, child.id, True, "Ba mẹ đã kết thúc phiên làm việc", client_ip(request))
    else:
        raise HTTPException(status_code=422, detail="Lệnh không được hỗ trợ")
    return {"status": "success", "command_id": payload["id"], "cmd": req.action}


@router.get("/commands/consent-status")
def get_consent_status(child_id: int, principal: Principal = Depends(require_parent), db: Session = Depends(get_db)):
    child = authorize_child(db, principal, child_id)
    return consent_status.get(child.id, {"feature": "screen", "status": "idle", "message": "Chưa có yêu cầu nào"})
