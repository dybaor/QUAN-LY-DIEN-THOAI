"""Hàm Windows CHỈ ĐỌC trong phiên đăng nhập của trẻ: nhàn rỗi, cửa sổ đang dùng, màn hình khóa.

Agent không khóa máy, không mở hộp thoại hay thao tác lên cửa sổ nào; mọi hiển thị cho trẻ nằm trong Cổng học tập (web).
"""

import ctypes
from ctypes import wintypes
from typing import Optional, Tuple

import psutil

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

DESKTOP_READOBJECTS = 0x0001


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def idle_seconds() -> float:
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return ((kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000.0


def foreground_process() -> Tuple[Optional[int], Optional[str], Optional[str]]:
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None, None, None
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value <= 4:
            return None, None, None
        proc = psutil.Process(pid.value)
        return pid.value, proc.name(), proc.exe()
    except (psutil.Error, OSError):
        return None, None, None


def is_session_locked() -> bool:
    """Màn hình khóa Windows (Win+L) đang hiển thị: không mở được desktop nhập liệu ở chế độ chỉ đọc."""
    desktop = user32.OpenInputDesktop(0, False, DESKTOP_READOBJECTS)
    if not desktop:
        return True
    user32.CloseDesktop(desktop)
    return False


def collect_state() -> dict:
    pid, name, exe = foreground_process()
    return {"idle_sec": idle_seconds(), "fg_pid": pid, "fg_name": name, "fg_exe": exe, "locked": is_session_locked()}
