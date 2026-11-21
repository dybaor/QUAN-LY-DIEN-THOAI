"""
OGK-Agent Network Client (KT-3, KT-4, KT-5, F4-2)
- Heartbeat mỗi 60 giây: gửi hạn mức đã dùng (`quota_used`), nhận `server_time` để đối chiếu đồng hồ.
- Kéo chính sách từ `/agent/policy` và chỉ nạp vào cache khi chữ ký HMAC-SHA256 hợp lệ.
- Gửi bù hàng đợi sự kiện kèm `idempotency_key`; chỉ xóa khỏi cache khi máy chủ xác nhận.
- WebSocket `/ws/agent` (Bearer token, TLS + ghim chứng chỉ) nhận lệnh khẩn: khóa, mở khóa, +giờ, xóa cache.
"""

import asyncio
import hashlib
import hmac
import json
import threading
import time
from datetime import date
from typing import Callable, Dict, Optional

import requests
import websockets

import settings
from local_cache import local_cache
from transport import AuthError, api, certificate_matches, websocket_ssl_context


def canonical_json(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def verify_policy_signature(envelope: dict, key: Optional[str], device_id: str) -> Optional[dict]:
    """Trả về chính sách nếu chữ ký hợp lệ và đúng thiết bị; ngược lại None."""
    policy, signature = envelope.get("policy"), envelope.get("signature", "")
    if not key or not isinstance(policy, dict) or envelope.get("algorithm") != "HMAC-SHA256":
        return None
    expected = hmac.new(key.encode("utf-8"), canonical_json(policy), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature) or policy.get("device_id") != device_id:
        return None
    return policy


class AgentNetworkClient:
    def __init__(self):
        self.is_online = False
        self.ui_present = True
        self._stop = threading.Event()
        self._flush_lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._current_ws = None
        self.handlers: Dict[str, Callable[[dict], None]] = {}
        self.on_server_time: Optional[Callable[[float, float, float], None]] = None

    def on(self, command: str, handler: Callable[[dict], None]):
        self.handlers[command] = handler

    def _dispatch(self, command: str, data: dict):
        handler = self.handlers.get(command)
        if handler:
            try:
                handler(data)
            except Exception as exc:
                print(f"[WS_HANDLER_ERROR] {command}: {exc}")

    # ---------- HTTP ----------
    def send_heartbeat(self) -> bool:
        if not local_cache.is_enrolled:
            return False
        policy = local_cache.get_policy() or {}
        today = date.today()
        payload = {
            "status": "online",
            "current_policy_version": policy.get("version", 0),
            "usage_day": today.isoformat(),
            "quota_used": local_cache.get_today_usage_seconds(today),
            "client_time": time.time(),
            "ui_present": self.ui_present,
        }
        try:
            started = time.time()
            resp = api.request("POST", "/heartbeat", json=payload)
            finished = time.time()
            if resp.status_code != 200:
                return False
            data = resp.json()
            self.is_online = True
            if self.on_server_time and data.get("server_epoch"):
                self.on_server_time(float(data["server_epoch"]), started, finished)
            # Điều chỉnh giờ trong ngày có thể đổi mà không tăng version nên luôn đồng bộ.
            self.sync_policy()
            self.flush_events()
            return True
        except AuthError as exc:
            print(f"[AUTH] {exc}")
        except (requests.RequestException, ValueError):
            pass
        self.is_online = False
        return False

    def sync_policy(self) -> bool:
        try:
            resp = api.request("GET", "/agent/policy")
            if resp.status_code != 200:
                return False
            policy = verify_policy_signature(resp.json(), local_cache.get_secret("policy_key"), local_cache.device_id)
        except (AuthError, requests.RequestException, ValueError):
            return False
        if policy is None:
            print("[SECURITY] Chữ ký chính sách không hợp lệ — giữ nguyên bản đang dùng.")
            return False
        cached = local_cache.get_policy() or {}
        if policy.get("version", 0) < cached.get("version", 0):
            print("[SECURITY] Từ chối chính sách cũ hơn bản đang dùng (chống phát lại).")
            return False
        local_cache.save_policy(policy)
        self._dispatch("policy_updated", policy)
        return True

    def flush_events(self, limit: int = 100) -> int:
        with self._flush_lock:
            events = local_cache.peek_events(limit)
            if not events:
                return 0
            batch = [{key: ev[key] for key in ("ts", "type", "subject", "duration_sec", "policy_id", "idempotency_key")}
                     for ev in events]
            try:
                resp = api.request("POST", "/events/batch", json=batch)
            except (AuthError, requests.RequestException):
                return 0
            if resp.status_code in (200, 201):
                local_cache.delete_events([ev["id"] for ev in events])
                return len(batch)
            return 0

    def send_message(self, data: dict) -> bool:
        if self._current_ws and self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._current_ws.send(json.dumps(data)), self._loop)
            return True
        return False

    # ---------- WebSocket ----------
    async def _ws_loop(self):
        while not self._stop.is_set():
            token = local_cache.get_secret("access_token")
            if not token:
                await asyncio.sleep(5)
                continue
            try:
                async with websockets.connect(settings.WS_URL, additional_headers={"Authorization": f"Bearer {token}"},
                                              ssl=websocket_ssl_context(), ping_interval=20, ping_timeout=20) as ws:
                    if not certificate_matches(ws):
                        print("[SECURITY] Chứng chỉ máy chủ không khớp vân tay đã ghim — ngắt kết nối.")
                        await ws.close()
                        await asyncio.sleep(30)
                        continue
                    self._current_ws = ws
                    self.is_online = True
                    print(f"[WS] Đã kết nối {settings.WS_URL}")
                    await asyncio.to_thread(self.sync_policy)
                    await asyncio.to_thread(self.flush_events)
                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                        except ValueError:
                            continue
                        command = data.get("cmd") or data.get("action")
                        if command:
                            await asyncio.to_thread(self._dispatch, command, data)
            except websockets.exceptions.InvalidStatus as exc:
                if getattr(exc.response, "status_code", 0) in (401, 403):
                    await asyncio.to_thread(self._refresh_or_flag)
            except (OSError, websockets.exceptions.WebSocketException):
                pass
            finally:
                self._current_ws = None
            await asyncio.sleep(5)

    def _refresh_or_flag(self):
        try:
            if not api.refresh():
                print("[AUTH] Thiết bị cần được ghép đôi lại.")
        except requests.RequestException:
            pass

    def start(self):
        def run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self._ws_loop())
            finally:
                self._loop.close()

        threading.Thread(target=run, name="WSClientThread", daemon=True).start()

    def stop(self):
        self._stop.set()
        self.flush_events()


ws_client = AgentNetworkClient()
