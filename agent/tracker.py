"""
OGK-Agent Screen-time Tracker (F1-3, F1-5)
- Đếm giờ bằng `time.monotonic()`; không đếm khi màn hình Windows đang khóa hoặc nhàn rỗi > 5 phút.
- Trạng thái phiên (nhàn rỗi, ứng dụng đang dùng, màn hình khóa) lấy từ UI bridge: khay hệ thống báo về khi
  chạy dạng Service, hoặc đọc trực tiếp khi chạy debug trong phiên người dùng.
- Chống chỉnh đồng hồ: so sánh time.time() với time.monotonic() và đối chiếu `server_time` từ heartbeat.
"""

import time
from typing import Optional, Tuple

import settings
from local_cache import local_cache


class ScreenTimeTracker:
    def __init__(self, idle_threshold_sec: int = settings.IDLE_THRESHOLD_SEC):
        self.idle_threshold_sec = idle_threshold_sec
        self.last_monotonic = time.monotonic()
        self.current_app_name: Optional[str] = None
        self.current_app_start_mono = time.monotonic()
        self.is_idle = False
        self.is_screen_locked = False
        self.base_wall_time = time.time()
        self.base_mono_time = time.monotonic()
        self.server_skew_reported = False

    # ---------- Chống chỉnh đồng hồ ----------
    def check_clock_tamper(self, threshold_sec: float = 60.0) -> Optional[float]:
        """Phát hiện đồng hồ hệ thống bị lùi so với đồng hồ monotonic (> threshold giây)."""
        now_mono, now_wall = time.monotonic(), time.time()
        skew = (now_mono - self.base_mono_time) - (now_wall - self.base_wall_time)
        if skew > threshold_sec:
            local_cache.enqueue_event("clock_tamper", f"Đồng hồ hệ thống bị lùi {int(skew)} giây", int(skew))
            self.base_wall_time, self.base_mono_time = now_wall, now_mono
            return skew
        if now_mono - self.base_mono_time > 600.0:
            self.base_wall_time, self.base_mono_time = now_wall, now_mono
        return None

    def check_server_time(self, server_epoch: float, request_started: float, request_finished: float) -> Optional[float]:
        """Đối chiếu đồng hồ máy với giờ máy chủ nhận từ heartbeat (bù nửa thời gian khứ hồi)."""
        local_mid = (request_started + request_finished) / 2
        skew = local_mid - server_epoch
        if abs(skew) > settings.CLOCK_SKEW_LIMIT_SEC:
            if not self.server_skew_reported:
                direction = "chậm" if skew < 0 else "nhanh"
                local_cache.enqueue_event("clock_tamper", f"Đồng hồ máy {direction} {int(abs(skew))} giây so với máy chủ",
                                          int(abs(skew)))
                self.server_skew_reported = True
            return skew
        self.server_skew_reported = False
        return None

    # ---------- Đếm giờ ----------
    def _close_current_app(self, now_mono: float):
        if self.current_app_name:
            duration = int(round(now_mono - self.current_app_start_mono))
            if duration >= 2:
                local_cache.enqueue_event("app_stop", self.current_app_name, duration)
        self.current_app_name = None

    def tick(self, state: Optional[dict], counting: bool = True) -> Tuple[float, bool]:
        """Chu kỳ 1 giây. Trả về (số giây được tính, có đang tạm dừng đếm không)."""
        now_mono = time.monotonic()
        delta = now_mono - self.last_monotonic
        self.last_monotonic = now_mono
        if delta < 0 or delta > 10.0:
            delta = 1.0

        if not state or not counting:
            self._close_current_app(now_mono)
            return 0.0, True

        self.is_screen_locked = bool(state.get("locked"))
        self.is_idle = (state.get("idle_sec") or 0) >= self.idle_threshold_sec
        if self.is_screen_locked or self.is_idle:
            self._close_current_app(now_mono)
            return 0.0, True

        name = state.get("fg_name")
        if name and name != self.current_app_name:
            self._close_current_app(now_mono)
            self.current_app_name = name
            self.current_app_start_mono = now_mono
            local_cache.enqueue_event("app_start", name, 0)

        seconds = int(round(delta))
        if name and seconds > 0:
            local_cache.add_daily_usage(seconds)
            return float(seconds), False
        return 0.0, False

    def finalize_current_app(self) -> None:
        self._close_current_app(time.monotonic())


tracker = ScreenTimeTracker()
