"""
OGK Tray UI — biểu tượng khay hệ thống chạy trong phiên đăng nhập của trẻ (KT-1, F5-6).

- Luôn hiển thị biểu tượng OGK để trẻ biết máy đang được quản lý (không có chế độ ẩn).
- KHÔNG khóa máy, KHÔNG mở hộp thoại hay thông báo hệ điều hành. Mọi hiển thị cho trẻ nằm trong Cổng học tập (web).
- Tooltip cho biết thời gian còn lại; menu chuột phải chỉ có mục mở Cổng học tập trên trình duyệt.
- Mỗi giây gửi trạng thái phiên (nhàn rỗi, ứng dụng đang dùng, màn hình khóa) tới Agent Service qua named pipe.

Chạy: `python tray_ui.py` (install_service.bat đăng ký tự khởi động khi người dùng đăng nhập).
"""

import json
import os
import sys
import threading
import time
import webbrowser

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import win32api
import win32con
import win32gui

import settings
import win_session

WM_TRAY = win32con.WM_USER + 20
MENU_PORTAL = 1001
BASE_TIP = "OGK Người Bạn Đồng Hành — máy đang được ba mẹ quản lý"


def tooltip_text(status: dict) -> str:
    if status.get("paused"):
        extra = "Ba mẹ đang cho tạm nghỉ giới hạn"
    elif status.get("state") == "locked":
        extra = "Đang khóa trong Cổng học tập"
    elif "remaining_min" in status:
        extra = f"Còn {status['remaining_min']} phút hôm nay"
    else:
        return BASE_TIP
    return f"{BASE_TIP}\n{extra}"[:127]


class TrayApp:
    def __init__(self):
        self.hwnd = None
        self.status = {}
        self._icon = None
        self._ready = threading.Event()

    def start_in_thread(self):
        threading.Thread(target=self.run, name="OGKTray", daemon=True).start()
        self._ready.wait(5)
        return self

    def alive(self) -> bool:
        return bool(self.hwnd) and bool(win32gui.IsWindow(self.hwnd))

    def run(self):
        wc = win32gui.WNDCLASS()
        wc.hInstance = win32api.GetModuleHandle(None)
        wc.lpszClassName = f"OGKTrayWindow{os.getpid()}"
        wc.lpfnWndProc = {WM_TRAY: self._on_tray, win32con.WM_COMMAND: self._on_command,
                          win32con.WM_DESTROY: self._on_destroy}
        atom = win32gui.RegisterClass(wc)
        self.hwnd = win32gui.CreateWindow(atom, "OGK", 0, 0, 0, 0, 0, 0, 0, wc.hInstance, None)
        self._icon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
        flags = win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, (self.hwnd, 0, flags, WM_TRAY, self._icon, BASE_TIP))
        self._ready.set()
        win32gui.PumpMessages()

    def _on_destroy(self, hwnd, msg, wparam, lparam):
        win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (hwnd, 0))
        win32gui.PostQuitMessage(0)
        return 0

    def _on_tray(self, hwnd, msg, wparam, lparam):
        if lparam in (win32con.WM_RBUTTONUP, win32con.WM_LBUTTONUP):
            menu = win32gui.CreatePopupMenu()
            win32gui.AppendMenu(menu, win32con.MF_STRING, MENU_PORTAL, "Mở Cổng học tập của em")
            x, y = win32gui.GetCursorPos()
            win32gui.SetForegroundWindow(hwnd)
            win32gui.TrackPopupMenu(menu, win32con.TPM_LEFTALIGN, x, y, 0, hwnd, None)
            win32gui.PostMessage(hwnd, win32con.WM_NULL, 0, 0)
        return 0

    def _on_command(self, hwnd, msg, wparam, lparam):
        if win32api.LOWORD(wparam) == MENU_PORTAL:
            webbrowser.open(settings.SERVER_URL + "/child")
        return 0

    def set_status(self, status: dict):
        """Cập nhật tooltip (chỉ khi nội dung đổi)."""
        text = tooltip_text(status)
        if text == tooltip_text(self.status) or not self.hwnd:
            self.status = dict(status)
            return
        self.status = dict(status)
        win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, (self.hwnd, 0, win32gui.NIF_TIP, WM_TRAY, self._icon, text))


def pipe_loop(app: TrayApp):
    """Gửi trạng thái phiên và nhận trạng thái hiển thị từ Agent Service mỗi giây."""
    import pywintypes
    import win32pipe

    while True:
        request = json.dumps({"state": win_session.collect_state()}).encode("utf-8")
        try:
            raw = win32pipe.CallNamedPipe(settings.PIPE_NAME, request, 65536, 2000)
            reply = json.loads(raw.decode("utf-8"))
            if reply.get("status"):
                app.set_status(reply["status"])
        except (pywintypes.error, ValueError):
            pass  # Service chưa chạy hoặc đang khởi động lại
        time.sleep(1)


def main():
    app = TrayApp().start_in_thread()
    pipe_loop(app)


if __name__ == "__main__":
    main()
