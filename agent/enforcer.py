"""
OGK-Agent Time Enforcer (F1-1, F1-2, F1-4, KT-4)
- Hạn mức ngày thường / cuối tuần + điều chỉnh trong ngày; lịch tuần 7 x 48 khung 30 phút.
- Cảnh báo trước 10, 5, 1 phút: ghi sự kiện `quota_warning` (Cổng học tập tự hiện cảnh báo cho trẻ).
- Ân hạn 60 giây để trẻ lưu bài rồi ghi sự kiện `locked`. Agent KHÔNG khóa Windows: việc khóa là overlay trên
  Cổng học tập, do máy chủ quyết định theo hạn mức, lịch tuần và lệnh của phụ huynh.
- Chế độ tạm nghỉ của phụ huynh tạm ngưng mọi giới hạn.
"""

import datetime
import time
from typing import Callable, Optional

import settings

SLOTS_PER_DAY = 48
SLOT_SECONDS = 1800
UNLIMITED = 10 ** 9


def schedule_slot(now: datetime.datetime) -> int:
    return now.weekday() * SLOTS_PER_DAY + now.hour * 2 + now.minute // 30


def expand_schedule(matrix: str) -> str:
    matrix = (matrix or "").strip()
    if len(matrix) == 168:
        return "".join(slot * 2 for slot in matrix)
    return matrix if len(matrix) == 7 * SLOTS_PER_DAY else "1" * (7 * SLOTS_PER_DAY)


def seconds_until_blocked(matrix: str, now: datetime.datetime) -> int:
    """Số giây còn lại đến khi lịch tuần chuyển sang giờ nghỉ (0 nếu hiện đang là giờ nghỉ)."""
    matrix = expand_schedule(matrix)
    slot = schedule_slot(now)
    if matrix[slot] != "1":
        return 0
    into_slot = (now.minute % 30) * 60 + now.second
    total = SLOT_SECONDS - into_slot
    for step in range(1, SLOTS_PER_DAY + 1):
        if matrix[(slot + step) % len(matrix)] != "1":
            return total
        total += SLOT_SECONDS
    return UNLIMITED


def is_paused(policy: dict, now_utc: Optional[datetime.datetime] = None) -> bool:
    value = (policy or {}).get("paused_until")
    if not value:
        return False
    try:
        until = datetime.datetime.fromisoformat(value.rstrip("Z"))
    except ValueError:
        return False
    return until > (now_utc or datetime.datetime.utcnow())


def quota_seconds(policy: dict, now: datetime.datetime) -> int:
    weekend = now.weekday() >= 5
    minutes = policy.get("daily_quota_weekend_min" if weekend else "daily_quota_weekday_min", 180 if weekend else 120)
    if policy.get("adjustment_date") == now.date().isoformat():
        minutes += policy.get("adjustment_minutes") or 0
    return max(0, int(minutes)) * 60


class TimeEnforcer:
    def __init__(self, blocker, enqueue: Callable, clock: Callable[[], float] = time.monotonic):
        self.blocker = blocker
        self.enqueue = enqueue
        self.clock = clock
        self.warned = set()
        self.grace_deadline: Optional[float] = None
        self.locked_reason: Optional[str] = None
        self.had_time = False
        self.day = None
        self.manual_lock: Optional[str] = None

    def reset(self):
        self.warned.clear()
        self.grace_deadline = None
        self.locked_reason = None

    def _lock(self, reason: str, record: bool = True):
        """Ghi nhận trạng thái khóa một lần cho mỗi lý do (không thao tác lên Windows)."""
        if self.locked_reason != reason:
            self.blocker.enforce_lock(reason, record=record)
            self.locked_reason = reason

    def evaluate(self, policy: Optional[dict], used_seconds: int, now: Optional[datetime.datetime] = None) -> dict:
        """Gọi mỗi giây. Trả về trạng thái để hiển thị trên khay hệ thống."""
        now = now or datetime.datetime.now()
        if self.day != now.date():
            self.day = now.date()
            self.reset()
        if not policy:
            return {"state": "no_policy"}
        if is_paused(policy):
            self.reset()
            return {"state": "paused", "paused": True}

        manual = self.manual_lock or policy.get("lock_reason")
        if manual:
            self.grace_deadline = None
            self._lock(f"Ba mẹ đã khóa máy: {manual}", record=False)  # Máy chủ đã ghi sự kiện khi phụ huynh bấm khóa
            return {"state": "locked", "reason": manual}

        remaining_quota = quota_seconds(policy, now) - used_seconds
        until_block = seconds_until_blocked(policy.get("schedule_matrix", ""), now)
        time_left = min(remaining_quota, until_block)
        reason = ("Đã hết thời gian sử dụng trong ngày" if remaining_quota <= until_block
                  else "Đã đến giờ nghỉ theo lịch của ba mẹ")
        status = {"state": "active", "remaining_min": max(0, remaining_quota) // 60, "used_min": used_seconds // 60}

        if time_left > 0:
            if self.locked_reason or self.grace_deadline:
                self.reset()  # Phụ huynh vừa cộng thêm giờ hoặc lịch cho phép trở lại
            self.had_time = True
            self.warned = {m for m in self.warned if time_left <= m * 60 + 60}  # Được cộng giờ → cảnh báo lại
            for threshold in sorted(settings.WARNING_MINUTES):
                if time_left <= threshold * 60 and threshold not in self.warned:
                    self.warned.update(m for m in settings.WARNING_MINUTES if m >= threshold)
                    left = -(-time_left // 60)
                    message = (f"Còn {left} phút nữa là {'hết giờ' if remaining_quota <= until_block else 'đến giờ nghỉ'}."
                               " Em nhớ lưu bài nhé!")
                    self.enqueue("quota_warning", message, time_left, policy.get("id"))
                    break
            return status

        if self.locked_reason:
            return {**status, "state": "locked", "reason": self.locked_reason}
        if not self.had_time:
            # Vừa đăng nhập khi đã hết giờ / ngoài lịch: không có cảnh báo trước nên ghi nhận khóa ngay.
            self._lock(reason)
            return {**status, "state": "locked", "reason": reason}
        if self.grace_deadline is None:
            self.grace_deadline = self.clock() + settings.GRACE_PERIOD_SEC
        if self.clock() >= self.grace_deadline:
            self._lock(reason)
            return {**status, "state": "locked", "reason": reason}
        return {**status, "state": "grace", "grace_left": int(self.grace_deadline - self.clock())}
