"""
OGK-Agent Screen-time Tracker Module (Thành viên A - Đo giờ & Chống lùi giờ)
- BẮT BUỘC dùng `time.monotonic()` chống gian lận lùi giờ hệ thống.
- Phát hiện nhàn rỗi (Idle Detection) bằng Windows API `GetLastInputInfo` (> 5 phút).
- Chuyên đề M6: Kiểm tra độ lệch giữa time.time() và time.monotonic(). Nếu phát hiện đồng hồ
  hệ thống bị lùi > 60 giây, tự động phát sinh sự kiện vi phạm type="clock_tamper".
"""

import ctypes
import os
import time
from typing import Optional, Tuple
import psutil
from local_cache import local_cache


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("dwTime", ctypes.c_uint),
    ]


class ScreenTimeTracker:
    """Bộ theo dõi thời gian thực màn hình và ứng dụng Foreground (M6 Compliant)."""

    def __init__(self, idle_threshold_sec: int = 300):
        self.idle_threshold_sec = idle_threshold_sec
        self.last_monotonic = time.monotonic()
        self.current_app_name: Optional[str] = None
        self.current_app_exe: Optional[str] = None
        self.current_app_pid: Optional[int] = None
        self.current_app_start_mono: float = time.monotonic()
        self.is_idle: bool = False

        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32

        # --- M6: Điểm chuẩn chống gian lận lùi giờ hệ thống ---
        self.base_wall_time: float = time.time()
        self.base_mono_time: float = time.monotonic()

    def get_idle_seconds(self) -> float:
        """Đo thời gian không có tương tác phím/chuột qua GetLastInputInfo."""
        try:
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if self._user32.GetLastInputInfo(ctypes.byref(lii)):
                current_tick = self._kernel32.GetTickCount()
                elapsed_ms = (current_tick - lii.dwTime) & 0xFFFFFFFF
                return elapsed_ms / 1000.0
        except Exception:
            pass
        return 0.0

    def check_clock_tamper(self, threshold_sec: float = 60.0) -> Optional[float]:
        """Chuyên đề M6: Kiểm tra độ lệch giữa đồng hồ hệ thống và monotonic clock.
        
        Nếu trẻ lùi đồng hồ hệ thống > 60s, phát sinh sự kiện vi phạm 'clock_tamper'.
        """
        now_mono = time.monotonic()
        now_wall = time.time()

        elapsed_mono = now_mono - self.base_mono_time
        elapsed_wall = now_wall - self.base_wall_time

        skew_seconds = elapsed_mono - elapsed_wall

        if skew_seconds > threshold_sec:
            print(f"[M6_CLOCK_TAMPER] Phát hiện gian lận lùi đồng hồ hệ thống: {skew_seconds:.1f}s!")
            local_cache.enqueue_event(
                event_type="clock_tamper",
                subject=f"System clock shifted backward by {int(skew_seconds)}s",
                duration_sec=int(skew_seconds),
            )
            self.base_wall_time = now_wall
            self.base_mono_time = now_mono
            return skew_seconds

        if elapsed_mono > 600.0:
            self.base_wall_time = now_wall
            self.base_mono_time = now_mono

        return None

    def get_foreground_process_info(self) -> Tuple[Optional[int], Optional[str], Optional[str]]:
        """Lấy thông tin PID, tên và exe của cửa sổ đang ở Foreground."""
        try:
            hwnd = self._user32.GetForegroundWindow()
            if not hwnd:
                return None, None, None

            pid = ctypes.c_ulong()
            self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if not pid.value or pid.value <= 4:
                return None, None, None

            proc = psutil.Process(pid.value)
            return pid.value, proc.name(), proc.exe()
        except Exception:
            return None, None, None

    def tick(self) -> Tuple[float, bool]:
        """Chu kỳ đếm nhịp mỗi giây."""
        now_mono = time.monotonic()
        delta = now_mono - self.last_monotonic
        self.last_monotonic = now_mono

        if delta < 0 or delta > 10.0:
            delta = 1.0

        # 1. Chuyên đề M6: Kiểm tra lùi giờ
        self.check_clock_tamper(threshold_sec=60.0)

        # 2. Phát hiện nhàn rỗi (Idle Detection)
        idle_seconds = self.get_idle_seconds()
        if idle_seconds >= self.idle_threshold_sec:
            if not self.is_idle:
                self.is_idle = True
                print(f"[IDLE] Không tương tác {idle_seconds:.1f}s (> {self.idle_threshold_sec}s). Tạm dừng đếm giờ.")
            return 0.0, True

        if self.is_idle:
            self.is_idle = False
            print("[ACTIVE] Tương tác trở lại. Tiếp tục đếm giờ.")

        # 3. Theo dõi Foreground app
        pid, name, exe_path = self.get_foreground_process_info()

        if name and name != self.current_app_name:
            if self.current_app_name:
                app_duration = int(round(now_mono - self.current_app_start_mono))
                if app_duration >= 2:
                    local_cache.enqueue_event(
                        event_type="app_stop",
                        subject=self.current_app_name,
                        duration_sec=app_duration,
                    )

            self.current_app_name = name
            self.current_app_exe = exe_path
            self.current_app_pid = pid
            self.current_app_start_mono = now_mono
            local_cache.enqueue_event(
                event_type="app_start",
                subject=name,
                duration_sec=0,
            )

        # 4. Cộng dồn vào SQLite
        additional_sec = int(round(delta))
        if name and additional_sec > 0:
            local_cache.add_daily_usage(additional_sec)

        return delta, False

    def finalize_current_app(self) -> None:
        """Chốt thời gian app hiện tại khi tắt máy."""
        if self.current_app_name:
            now_mono = time.monotonic()
            app_duration = int(round(now_mono - self.current_app_start_mono))
            if app_duration > 0:
                local_cache.enqueue_event(
                    event_type="app_stop",
                    subject=self.current_app_name,
                    duration_sec=app_duration,
                )
            self.current_app_name = None


tracker = ScreenTimeTracker()

