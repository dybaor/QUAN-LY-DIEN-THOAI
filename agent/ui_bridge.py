r"""Cầu nối giữa lõi Agent và biểu tượng khay hệ thống (KT-1).

- `PipeBridge`: dùng khi Agent chạy là Windows Service (phiên 0, không có màn hình). Service mở named pipe
  `\\.\pipe\OGKAgentUI`; tiến trình khay (`tray_ui.py`) trong phiên của trẻ gọi mỗi giây để gửi trạng thái phiên
  (nhàn rỗi, ứng dụng đang dùng, màn hình khóa) và nhận trạng thái hiển thị ở tooltip.
- `LocalBridge`: dùng khi chạy `main_service.py debug` ngay trong phiên người dùng.

Cầu nối chỉ chuyển dữ liệu. Không có lệnh khóa máy hay mở hộp thoại: Agent chỉ ghi sự kiện, còn phần hiển thị
cho trẻ (khóa, cảnh báo, lý do chặn) nằm hoàn toàn trong Cổng học tập (overlay web).
Cầu nối cũng cho biết khay có đang hiện diện không để Agent tự dừng giám sát khi mất UI (F5-6).
"""

import json
import threading
import time
from typing import Optional

import settings


class UIBridge:
    def state(self) -> Optional[dict]:
        raise NotImplementedError

    def present(self) -> bool:
        raise NotImplementedError

    def publish_status(self, status: dict) -> None:
        """Thông tin hiển thị ở tooltip khay (thời gian còn lại, trạng thái tạm nghỉ...)."""


class LocalBridge(UIBridge):
    def __init__(self, tray=None):
        import win_session
        self._win = win_session
        self.tray = tray

    def state(self):
        return self._win.collect_state()

    def present(self):
        return self.tray is None or self.tray.alive()

    def publish_status(self, status):
        if self.tray:
            self.tray.set_status(status)


class PipeBridge(UIBridge):
    def __init__(self, pipe_name: str = settings.PIPE_NAME):
        self.pipe_name = pipe_name
        self._status = {}
        self._state: Optional[dict] = None
        self._last_seen = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def state(self):
        with self._lock:
            return dict(self._state) if self._state and self.present() else None

    def present(self):
        return time.monotonic() - self._last_seen < settings.UI_MISSING_LIMIT_SEC

    def publish_status(self, status):
        with self._lock:
            self._status = dict(status)

    # Máy chủ named pipe
    def handle_request(self, raw: bytes) -> bytes:
        try:
            request = json.loads(raw.decode("utf-8"))
        except ValueError:
            request = {}
        with self._lock:
            if isinstance(request.get("state"), dict):
                self._state = request["state"]
            self._last_seen = time.monotonic()
            status = dict(self._status)
        return json.dumps({"status": status}, ensure_ascii=False).encode("utf-8")

    def start(self):
        self._thread = threading.Thread(target=self._serve, name="OGKPipeServer", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _serve(self):
        import pywintypes
        import win32file
        import win32pipe
        import win32security

        # SYSTEM & Administrators toàn quyền; người dùng đăng nhập tương tác (IU) được đọc/ghi.
        descriptor = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
            "D:(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGW;;;IU)", win32security.SDDL_REVISION_1)
        attributes = win32security.SECURITY_ATTRIBUTES()
        attributes.SECURITY_DESCRIPTOR = descriptor
        while not self._stop.is_set():
            handle = None
            try:
                handle = win32pipe.CreateNamedPipe(
                    self.pipe_name, win32pipe.PIPE_ACCESS_DUPLEX,
                    win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
                    1, 65536, 65536, 0, attributes)
                win32pipe.ConnectNamedPipe(handle, None)
                _, data = win32file.ReadFile(handle, 65536)
                win32file.WriteFile(handle, self.handle_request(data))
                win32file.FlushFileBuffers(handle)
            except pywintypes.error:
                time.sleep(0.5)
            finally:
                if handle is not None:
                    try:
                        win32pipe.DisconnectNamedPipe(handle)
                    except pywintypes.error:
                        pass
                    win32file.CloseHandle(handle)
