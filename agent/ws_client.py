"""
OGK-Agent WebSocket Client & Server Communication (Thành viên A - Realtime & Sync)
- Kết nối WebSocket ws://127.0.0.1:8000/ws/{device_id} lắng nghe lệnh lock_now (< 5s).
- Gửi Heartbeat định kỳ mỗi 60 giây lên POST /heartbeat.
- Tự động đẩy hàng đợi sự kiện (Events Ingestion 7 trường) lên POST /events/batch.
- Tự động đồng bộ Policy từ GET /policy/{child_id}.
"""

import asyncio
import json
import threading
import time
from typing import Any, Dict, List, Optional
import requests
import websockets
from blocker import blocker
from local_cache import local_cache


class AgentNetworkClient:
    """Quản lý kết nối mạng và WebSocket cho Agent."""

    def __init__(self, server_url: str = "http://127.0.0.1:8000", ws_url: str = "ws://127.0.0.1:8000/ws"):
        self.server_url = server_url
        self.ws_url = ws_url
        self.device_id = local_cache.device_id
        self.child_id = local_cache.child_id
        self.is_online = False
        self._stop_event = threading.Event()
        self._ws_thread: Optional[threading.Thread] = None
        self._current_ws = None
        self._loop = None
        self.consent_callback = None
        self.policy_callback = None
        self.shutdown_callback = None
        self.lock_callback = None
        self.unlock_callback = None
        self.close_session_callback = None
        self.deduct_callback = None

    def set_consent_callback(self, cb):
        self.consent_callback = cb

    def set_policy_callback(self, cb):
        self.policy_callback = cb

    def set_shutdown_callback(self, cb):
        self.shutdown_callback = cb

    def set_lock_callback(self, cb):
        self.lock_callback = cb

    def set_unlock_callback(self, cb):
        self.unlock_callback = cb

    def set_close_session_callback(self, cb):
        self.close_session_callback = cb

    def set_deduct_callback(self, cb):
        self.deduct_callback = cb

    def send_response(self, data: dict) -> bool:
        """Gửi thông điệp phản hồi ngược lại Server qua WebSocket hoặc HTTP."""
        if self._current_ws and self._loop and self._loop.is_running():
            try:
                msg = json.dumps(data)
                asyncio.run_coroutine_threadsafe(self._current_ws.send(msg), self._loop)
                return True
            except Exception:
                pass
        # Fallback qua HTTP nếu WS bận
        try:
            if data.get("type") == "consent_response":
                requests.post(f"{self.server_url}/commands/consent-response", json=data, timeout=3.0)
                return True
        except Exception:
            pass
        return False

    def send_heartbeat(self) -> bool:
        """Gửi heartbeat lên server mỗi 60s và đồng bộ chính sách khi có version mới."""
        policy = local_cache.get_policy()
        ver = policy.get("version", 1) if policy else 1
        payload = {
            "device_id": self.device_id,
            "status": "online",
            "current_policy_version": ver,
        }
        try:
            resp = requests.post(f"{self.server_url}/heartbeat", json=payload, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                self.is_online = True
                latest_ver = data.get("latest_version", ver)
                if data.get("need_policy_update", False) or latest_ver > ver or not policy:
                    print(f"[SYNC] Phát hiện chính sách mới (v{latest_ver} > v{ver}), tiến hành đồng bộ...")
                    self.sync_policy()
                self.flush_events()
                return True
        except Exception:
            self.is_online = False
        return False

    def sync_policy(self) -> bool:
        """Kéo chính sách mới từ server về lưu vào cache SQLite."""
        try:
            resp = requests.get(f"{self.server_url}/policy/{self.child_id}", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                local_cache.save_policy(data)
                print(f"[SYNC_SUCCESS] Đã đồng bộ chính sách v{data.get('version')} vào SQLite cache.")
                return True
        except Exception as e:
            print(f"[SYNC_ERROR] Lỗi đồng bộ chính sách: {e}")
        return False

    def flush_events(self, limit: int = 50) -> int:
        """Đẩy các sự kiện ngoại tuyến lên Server theo lô 7 trường chuẩn.
        Chỉ xóa khỏi SQLite khi Server trả về HTTP 200 hoặc 201."""
        events = local_cache.peek_events(limit)
        if not events:
            return 0
        batch_payload = [
            {
                "ts": ev["ts"],
                "device_id": ev["device_id"],
                "child_id": ev["child_id"],
                "type": ev["type"],
                "subject": ev["subject"],
                "duration_sec": ev["duration_sec"],
                "policy_id": ev["policy_id"],
            }
            for ev in events
        ]
        ids = [ev["id"] for ev in events]
        try:
            resp = requests.post(f"{self.server_url}/events/batch", json=batch_payload, timeout=8.0)
            if resp.status_code in (200, 201):
                local_cache.delete_events(ids)
                return len(batch_payload)
            # Thử endpoint fallback /events/
            resp2 = requests.post(f"{self.server_url}/events/", json=batch_payload, timeout=8.0)
            if resp2.status_code in (200, 201):
                local_cache.delete_events(ids)
                return len(batch_payload)
        except Exception:
            pass
        return 0

    async def _ws_loop(self):
        ws_uri = f"{self.ws_url}/{self.device_id}"
        while not self._stop_event.is_set():
            try:
                async with websockets.connect(ws_uri, ping_interval=20, ping_timeout=20) as ws:
                    self._current_ws = ws
                    print(f"[WS] Kết nối WebSocket thành công tới {ws_uri}")
                    self.is_online = True
                    # Vừa kết nối là đồng bộ policy ngay
                    self.sync_policy()
                    self.flush_events()

                    while not self._stop_event.is_set():
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                            data = json.loads(msg)
                            cmd = data.get("cmd") or data.get("action")
                            reason = data.get("reason", "Lệnh từ phụ huynh")
                            if cmd in ("lock_now", "lock_window", "lock_app"):
                                print(f"[WS_COMMAND] Nhận lệnh khóa cửa sổ ({cmd})! Lý do: {reason}")
                                if self.lock_callback:
                                    self.lock_callback(reason)
                                else:
                                    blocker.show_user_popup("KHÓA CỬA SỔ", f"Ba mẹ đã tạm khóa phiên làm việc ({reason}).")
                            elif cmd in ("unlock_window", "unlock"):
                                print(f"[WS_COMMAND] Nhận lệnh mở khóa cửa sổ ({cmd})!")
                                if self.unlock_callback:
                                    self.unlock_callback(reason)
                                else:
                                    blocker.show_user_popup("MỞ KHÓA", "Ba mẹ đã mở khóa cửa sổ.")
                            elif cmd in ("close_session", "quit_launcher"):
                                print(f"[WS_COMMAND] Nhận lệnh đóng phiên làm việc ({cmd})!")
                                if self.close_session_callback:
                                    self.close_session_callback(reason)
                            elif cmd == "shutdown_now":
                                timeout_sec = data.get("timeout_sec", 10)
                                print(f"[WS_COMMAND] Nhận lệnh shutdown_now -> Chuyển thành đóng phiên làm việc...")
                                if self.close_session_callback:
                                    self.close_session_callback(reason)
                                elif self.shutdown_callback:
                                    self.shutdown_callback(timeout_sec, reason)
                            elif cmd == "cancel_shutdown":
                                print(f"[WS_COMMAND] Nhận lệnh cancel_shutdown! Hủy lệnh...")
                                blocker.cancel_shutdown()
                            elif cmd in ("time_deducted", "deduct_time"):
                                deduct_min = data.get("deduct_min") or data.get("minutes") or 15
                                print(f"[WS_COMMAND] Nhận thông báo trừ giờ: -{deduct_min} phút!")
                                self.sync_policy()
                                if self.deduct_callback:
                                    self.deduct_callback(deduct_min, reason)
                                if self.policy_callback:
                                    self.policy_callback("time_deducted", data)
                            elif cmd == "request_screen_consent":
                                print(f"[WS_COMMAND] Nhận yêu cầu đồng thuận xem màn hình...")
                                if self.consent_callback:
                                    self.consent_callback(reason)
                                else:
                                    blocker.show_user_popup("YÊU CẦU ĐỒNG THUẬN", f"Ba mẹ đang yêu cầu xem màn hình của bạn ({reason}).")
                            elif cmd in ("sync_policy", "extend_time"):
                                print(f"[WS_COMMAND] Nhận lệnh {cmd}! Đồng bộ chính sách mới tức thì...")
                                self.sync_policy()
                                if self.policy_callback:
                                    self.policy_callback(cmd, data)
                        except asyncio.TimeoutError:
                            continue
                        except websockets.exceptions.ConnectionClosed:
                            break
            except Exception:
                pass
            finally:
                self._current_ws = None
            for _ in range(5):
                if self._stop_event.is_set():
                    break
                time.sleep(1)

    def start(self):
        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            try:
                loop.run_until_complete(self._ws_loop())
            finally:
                loop.close()

        self._ws_thread = threading.Thread(target=_run, name="WSClientThread", daemon=True)
        self._ws_thread.start()

    def stop(self):
        self._stop_event.set()
        try:
            self.flush_events()
        except Exception:
            pass


ws_client = AgentNetworkClient()

