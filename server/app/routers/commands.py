import json
from uuid import uuid4
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Device, Policy
from ..websocket_manager import manager

router = APIRouter(tags=["Commands & WebSocket"])

# Lưu trữ trạng thái đồng thuận mới nhất
latest_consent_status = {
    "feature": "screen",
    "status": "idle", # idle, pending, accepted, declined
    "timestamp": None,
    "message": "Chưa có yêu cầu nào"
}

# --- Models cho Lệnh & Heartbeat ---
class CommandRequest(BaseModel):
    device_id: str
    action: str  # "lock_now", "shutdown_now", "cancel_shutdown", "request_screen_consent", "unlock", "extend_time"
    duration_min: Optional[int] = 0
    reason: str = "Lệnh từ phụ huynh"

class HeartbeatRequest(BaseModel):
    device_id: str
    status: str = "online"
    current_policy_version: Optional[int] = 1

class ConsentResponseModel(BaseModel):
    feature: str = "screen"
    approved: bool
    reason: Optional[str] = ""

# --- 1. Endpoint Heartbeat từ Agent gửi lên ---
@router.post("/heartbeat")
def receive_heartbeat(req: HeartbeatRequest, db: Session = Depends(get_db)):
    """Agent định kỳ mỗi 60s gọi endpoint này để báo trạng thái online và kiểm tra version."""
    device = db.query(Device).filter(Device.id == req.device_id).first()
    child_id = device.child_id if device else 1
    policy = db.query(Policy).filter(Policy.child_id == child_id).first()
    need_update = False
    if policy and req.current_policy_version is not None:
        if policy.version > req.current_policy_version:
            need_update = True

    return {
        "status": "ack",
        "server_time": datetime.utcnow().isoformat(),
        "need_policy_update": need_update,
        "latest_version": policy.version if policy else 1
    }

# --- 2. Endpoint WebSocket giao tiếp thời gian thực ---
@router.websocket("/ws/{device_id}")
async def websocket_endpoint(websocket: WebSocket, device_id: str):
    await manager.connect(device_id, websocket)
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect(message.get("code", 1000))

            # Hỗ trợ nhận frame nhị phân từ websocket
            if "bytes" in message and message["bytes"]:
                await manager.send_bytes_to_parents(message["bytes"])
                continue

            # Lắng nghe phản hồi text/JSON từ Agent hoặc Parent Dashboard
            if "text" in message and message["text"]:
                data = message["text"]
                print(f"[WS Received from {device_id}]: {data}")
                try:
                    obj = json.loads(data)
                    action = obj.get("action") or obj.get("cmd") or obj.get("type")

                    # Chat 2 chiều thời gian thực (Hoạt động cả khi máy con bị khóa)
                    if action in ("chat_message", "chat"):
                        sender = obj.get("sender", "parent")
                        chat_payload = {
                            "cmd": "chat_message",
                            "message_id": obj.get("message_id") or uuid4().hex,
                            "sender": sender,
                            "text": obj.get("text", ""),
                            "timestamp": obj.get("timestamp") or datetime.utcnow().strftime("%H:%M:%S %d/%m/%Y")
                        }
                        if sender == "child":
                            await manager.send_to_parents(chat_payload)
                        else:
                            await manager.send_to_children(chat_payload)

                    # Cảnh báo vi phạm truy cập gửi tới phụ huynh
                    elif action in ("violation_alert", "violation"):
                        target_name = obj.get("target_name") or obj.get("target") or "Nội dung hạn chế"
                        target_type = obj.get("target_type", "web")
                        violation_type = obj.get("violation_type") or "Từ khóa / Tên miền cấm"
                        ts = obj.get("timestamp") or datetime.utcnow().strftime("%H:%M:%S %d/%m/%Y")
                        await manager.send_to_parents({
                            "cmd": "violation_alert",
                            "target_name": target_name,
                            "target_type": target_type,
                            "violation_type": violation_type,
                            "timestamp": ts,
                            "message": f"⚠️ Cảnh báo vi phạm! Bé vừa tìm kiếm/truy cập: {target_name} vào lúc {ts}"
                        })
                    elif action in ("parent_authenticated", "parent_login"):
                        await manager.send_to_children({
                            "cmd": "init_completed",
                            "child_id": obj.get("child_id", 1)
                        })
                    elif action in ("time_expired_alert", "time_expired"):
                        child_name = obj.get("child_name") or "Bé yêu"
                        ts = obj.get("timestamp") or datetime.utcnow().strftime("%H:%M:%S %d/%m/%Y")
                        await manager.send_to_parents({
                            "cmd": "time_expired_alert",
                            "child_name": child_name,
                            "timestamp": ts,
                            "message": f"Bé {child_name} đã dùng hết thời gian trong ngày!"
                        })

                    # Lệnh từ Dashboard phụ huynh -> chuyển tiếp riêng cho máy con
                    elif action in ("request_screen", "request_screen_consent"):
                        latest_consent_status["status"] = "pending"
                        latest_consent_status["timestamp"] = datetime.utcnow().isoformat()
                        latest_consent_status["message"] = "Đang gửi yêu cầu đồng thuận tới máy con của bé..."
                        await manager.send_to_children({
                            "cmd": "request_screen_consent",
                            "reason": obj.get("reason", "Ba mẹ muốn xem màn hình học tập của con")
                        })
                    elif action == "stop_screen_share":
                        await manager.send_to_children({
                            "cmd": "stop_screen_share"
                        })
                    elif action in ("lock", "lock_now", "lock_window"):
                        await manager.send_to_children({
                            "cmd": "lock_window",
                            "reason": obj.get("reason", "Lệnh từ phụ huynh")
                        })
                    elif action in ("unlock", "unlock_window"):
                        await manager.send_to_children({
                            "cmd": "unlock_window"
                        })
                    elif obj.get("type") == "consent_response":
                        approved = obj.get("approved", False)
                        latest_consent_status["status"] = "accepted" if approved else "declined"
                        latest_consent_status["timestamp"] = datetime.utcnow().isoformat()
                        latest_consent_status["message"] = "Bé đã ĐỒNG Ý chia sẻ màn hình" if approved else "Bé đã TỪ CHỐI chia sẻ màn hình"
                        await manager.send_to_parents({
                            "cmd": "screen_consent_result",
                            "approved": approved,
                            "message": latest_consent_status["message"]
                        })
                except Exception:
                    pass
    except WebSocketDisconnect:
        manager.disconnect(device_id, websocket)

@router.websocket("/ws/child/{guid}")
async def child_websocket_endpoint(websocket: WebSocket, guid: str):
    """Endpoint WebSocket chuyên biệt phục vụ Cửa sổ Trẻ em (Child Web Portal)."""
    device_key = f"child_{guid}"
    await manager.connect(device_key, websocket)
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect(message.get("code", 1000))

            # 1. Nhận dữ liệu nhị phân (Binary Frame 15-30 FPS) -> Chuyển thẳng tới Phụ huynh ngay lập tức
            if "bytes" in message and message["bytes"]:
                await manager.send_bytes_to_parents(message["bytes"])
                continue

            # 2. Nhận dữ liệu text / JSON
            if "text" in message and message["text"]:
                data = message["text"]
                try:
                    obj = json.loads(data)
                    msg_type = obj.get("type")
                    # 1. Phản hồi đồng thuận xem màn hình -> Gửi riêng cho Phụ huynh
                    if msg_type == "consent_response":
                        approved = obj.get("approved", False)
                        latest_consent_status["status"] = "accepted" if approved else "declined"
                        latest_consent_status["timestamp"] = datetime.utcnow().isoformat()
                        latest_consent_status["message"] = "Bé đã ĐỒNG Ý chia sẻ màn hình" if approved else "Bé đã TỪ CHỐI chia sẻ màn hình"
                        await manager.send_to_parents({
                            "cmd": "screen_consent_result",
                            "approved": approved,
                            "message": latest_consent_status["message"]
                        })
                    # 2. Truyền khung hình màn hình dạng Base64 (fallback) -> Gửi riêng cho Phụ huynh
                    elif msg_type == "screen_frame":
                        await manager.send_to_parents({
                            "cmd": "live_screen_frame",
                            "frame": obj.get("data")
                        })
                    # 3. Bé dừng chia sẻ màn hình -> Gửi riêng cho Phụ huynh
                    elif msg_type == "stop_screen_share":
                        await manager.send_to_parents({
                            "cmd": "screen_share_stopped"
                        })
                    # 4. Tin nhắn Chat từ Trẻ -> Gửi riêng cho Phụ huynh
                    elif msg_type in ("chat_message", "chat") or obj.get("action") in ("chat_message", "chat"):
                        await manager.send_to_parents({
                            "cmd": "chat_message",
                            "message_id": obj.get("message_id") or uuid4().hex,
                            "sender": "child",
                            "text": obj.get("text", ""),
                            "timestamp": obj.get("timestamp") or datetime.utcnow().strftime("%H:%M:%S %d/%m/%Y")
                        })
                    # 5. Cảnh báo vi phạm truy cập từ Trẻ -> Gửi riêng cho Phụ huynh
                    elif msg_type in ("violation_alert", "violation") or obj.get("action") in ("violation_alert", "violation"):
                        target_name = obj.get("target_name") or obj.get("target") or "Nội dung hạn chế"
                        target_type = obj.get("target_type", "web")
                        violation_type = obj.get("violation_type") or "Từ khóa / Tên miền cấm"
                        ts = obj.get("timestamp") or datetime.utcnow().strftime("%H:%M:%S %d/%m/%Y")
                        await manager.send_to_parents({
                            "cmd": "violation_alert",
                            "target_name": target_name,
                            "target_type": target_type,
                            "violation_type": violation_type,
                            "timestamp": ts,
                            "message": f"⚠️ Cảnh báo vi phạm! Bé vừa tìm kiếm/truy cập: {target_name} vào lúc {ts}"
                        })
                    # 6. Thông báo hết thời gian sử dụng từ Trẻ -> Gửi riêng cho Phụ huynh
                    elif msg_type in ("time_expired_alert", "time_expired") or obj.get("action") in ("time_expired_alert", "time_expired"):
                        child_name = obj.get("child_name") or "Bé yêu"
                        ts = obj.get("timestamp") or datetime.utcnow().strftime("%H:%M:%S %d/%m/%Y")
                        await manager.send_to_parents({
                            "cmd": "time_expired_alert",
                            "child_name": child_name,
                            "timestamp": ts,
                            "message": f"Bé {child_name} đã dùng hết thời gian trong ngày!"
                        })
                except Exception:
                    pass
    except WebSocketDisconnect:
        manager.disconnect(device_key, websocket)

# --- 3. Endpoint lấy danh sách thiết bị đang online qua WebSocket ---
@router.get("/devices/online")
def get_online_devices():
    """Lấy danh sách các thiết bị đang kết nối WebSocket thời gian thực"""
    return {"online_devices": [k for k, v in manager.active_connections.items() if v]}

# --- 4. Endpoint gửi lệnh khẩn cấp thống nhất định dạng ---
@router.post("/commands/send")
async def send_emergency_command(req: CommandRequest):
    # Chuẩn hóa format đúng chuẩn {"cmd": ..., "id": ...} mà nhóm yêu cầu
    payload = {
        "cmd": req.action,
        "id": f"CMD-{int(datetime.utcnow().timestamp())}",
        "reason": req.reason,
        "duration_min": req.duration_min,
        "timeout_sec": 10 if req.action == "shutdown_now" else 30
    }

    if req.action == "request_screen_consent":
        latest_consent_status["status"] = "pending"
        latest_consent_status["timestamp"] = datetime.utcnow().isoformat()
        latest_consent_status["message"] = "Đang gửi yêu cầu đồng thuận tới máy con của bé..."
        # CHỈ GỬI LỆNH XEM MÀN HÌNH TỚI CỬA SỔ CỦA TRẺ, TUYỆT ĐỐI KHÔNG BROADCAST VỀ PHỤ HUYNH
        await manager.send_to_children(payload)
        return {"status": "success", "command_id": payload["id"], "target_device": "children", "cmd": req.action}

    # Gửi lệnh trực tiếp hoặc phát broadcast cho toàn bộ client kết nối
    await manager.broadcast(payload)
    return {"status": "success", "command_id": payload["id"], "target_device": "broadcast", "cmd": req.action}

# --- 5. Endpoints quản lý phản hồi đồng thuận (Consent API) ---
@router.get("/commands/consent-status")
def get_consent_status():
    """Lấy trạng thái phản hồi đồng thuận mới nhất từ máy trẻ em"""
    return latest_consent_status

@router.post("/commands/consent-response")
def post_consent_response(res: ConsentResponseModel):
    """Máy con gửi phản hồi đồng thuận qua HTTP fallback"""
    latest_consent_status["status"] = "accepted" if res.approved else "declined"
    latest_consent_status["timestamp"] = datetime.utcnow().isoformat()
    latest_consent_status["message"] = "Bé đã ĐỒNG Ý chia sẻ màn hình" if res.approved else f"Bé đã TỪ CHỐI chia sẻ màn hình ({res.reason or 'Không đồng ý'})"
    return {"status": "success", "current_consent": latest_consent_status}
