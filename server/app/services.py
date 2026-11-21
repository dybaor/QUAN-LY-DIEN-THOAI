"""Nghiệp vụ dùng chung: tính quỹ thời gian, tuần tự hóa và ký chính sách, chuẩn hóa sự kiện."""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .categories import default_blocked_categories
from .daily_time import adjustment_minutes
from .models import AgentDailyUsage, Child, ChildWindowLock, DeviceEvent, Policy, WebDailyUsage
from .security import sign_payload

SLOTS_PER_DAY = 48
SCHEDULE_LENGTH = 7 * SLOTS_PER_DAY

# Tập giá trị `type` chuẩn của đặc tả (F3-1)
EVENT_TYPES = {
    "app_start", "app_stop", "domain_query", "blocked_app", "blocked_domain",
    "quota_warning", "locked", "unlock_request", "override_granted",
}
LEGACY_EVENT_TYPES = {
    "web_visit": "domain_query",
    "query_filter": "blocked_domain",
    "blocked_keyword": "blocked_domain",
    "quota_exceeded": "locked",
}
VIOLATION_TYPES = ("blocked_app", "blocked_domain", "locked")


def normalize_event_type(value: str) -> Optional[str]:
    value = (value or "").strip()
    return value if value in EVENT_TYPES else LEGACY_EVENT_TYPES.get(value)


def normalize_schedule(matrix: Optional[str]) -> str:
    """Chuẩn hóa lịch tuần về 336 ký tự (7 ngày x 48 khung 30 phút); lịch 168 ký tự cũ được nhân đôi từng giờ."""
    value = (matrix or "").strip()
    if len(value) == 168:
        value = "".join(slot * 2 for slot in value)
    if len(value) != SCHEDULE_LENGTH or set(value) - {"0", "1"}:
        raise ValueError("Lịch tuần phải có đúng 336 ký tự '0'/'1' (7 ngày x 48 khung 30 phút)")
    return value


def get_or_create_policy(db: Session, child: Child) -> Policy:
    policy = db.query(Policy).filter(Policy.child_id == child.id).first()
    if not policy:
        policy = Policy(child_id=child.id, child_name=child.name,
                        blocked_categories=default_blocked_categories(child.age))
        db.add(policy)
        db.commit()
        db.refresh(policy)
    return policy


def is_paused(policy: Optional[Policy], now: Optional[datetime] = None) -> bool:
    return bool(policy and policy.paused_until and policy.paused_until > (now or datetime.utcnow()))


def daily_usage_seconds(child_id: int, day: date, db: Session) -> int:
    start = datetime.combine(day, datetime.min.time())
    end = start + timedelta(days=1)
    # Sự kiện Agent lưu UTC; ranh giới ngày theo giờ địa phương của máy chủ.
    start_utc = datetime.utcfromtimestamp(start.timestamp())
    end_utc = datetime.utcfromtimestamp(end.timestamp())
    live_usage = db.query(AgentDailyUsage).filter_by(child_id=child_id, day=day)
    measured = live_usage.with_entities(func.sum(AgentDailyUsage.used_seconds)).scalar() or 0
    legacy = db.query(func.sum(DeviceEvent.duration_sec)).filter(
        DeviceEvent.child_id == child_id, DeviceEvent.type == "app_stop",
        DeviceEvent.ts >= start_utc, DeviceEvent.ts < end_utc,
        DeviceEvent.device_id.not_in(live_usage.with_entities(AgentDailyUsage.device_id).statement),
    ).scalar() or 0
    web = db.get(WebDailyUsage, (child_id, day))
    # Agent và cổng web có thể đo cùng một hoạt động nên lấy giá trị lớn nhất thay vì cộng dồn.
    return max(0, measured + legacy, int(web.used_seconds) if web else 0)


def schedule_allows_now(policy: Optional[Policy], now: datetime) -> bool:
    """Lịch tuần 7 x 48 khung 30 phút: thời điểm `now` có đang được phép dùng không."""
    if not policy or not policy.schedule_matrix:
        return True
    try:
        matrix = normalize_schedule(policy.schedule_matrix)
    except ValueError:
        return True
    return matrix[now.weekday() * SLOTS_PER_DAY + now.hour * 2 + now.minute // 30] == "1"


def time_snapshot(child_id: int, day: date, db: Session) -> dict:
    policy = db.query(Policy).filter(Policy.child_id == child_id).first()
    quota = 180 if day.weekday() >= 5 else 120
    if policy:
        quota = policy.daily_quota_weekend_min if day.weekday() >= 5 else policy.daily_quota_weekday_min
    adjustment = adjustment_minutes(db, child_id, day)
    effective_quota = max(0, quota + adjustment)
    used = daily_usage_seconds(child_id, day, db)
    lock = db.get(ChildWindowLock, child_id)
    paused = is_paused(policy)
    # Ngoài khung giờ cho phép: overlay web (không áp dụng khi phụ huynh đang cho tạm nghỉ)
    schedule_blocked = not paused and day == datetime.now().date() and not schedule_allows_now(policy, datetime.now())
    return {
        "lock_reason": lock.reason if lock else None,
        "schedule_blocked": schedule_blocked,
        "today_minutes": used // 60,
        "today_seconds": used,
        "quota_minutes": effective_quota,
        "base_quota_minutes": quota,
        "adjustment_minutes": adjustment,
        "remaining_seconds": max(0, effective_quota * 60 - used),
        "paused": paused,
        "paused_until": iso(policy.paused_until) if paused else None,
    }


def local_text(value: datetime) -> str:
    """Chuyển thời điểm UTC (naive) lưu trong DB sang giờ địa phương của máy chủ để hiển thị trong các bảng nhật ký."""
    local = value.replace(tzinfo=timezone.utc).astimezone()
    return local.strftime("%H:%M:%S %d/%m/%Y")


def iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() + "Z" if value else None


def policy_payload(db: Session, policy: Policy) -> dict:
    """Chính sách gửi cho client. Tuyệt đối không chứa mã PIN hay mã băm PIN."""
    day = datetime.now().date()
    lock = db.get(ChildWindowLock, policy.child_id)
    return {
        "id": policy.id,
        "child_id": policy.child_id,
        "child_name": policy.child_name,
        "version": policy.version,
        "daily_quota_weekday_min": policy.daily_quota_weekday_min,
        "daily_quota_weekend_min": policy.daily_quota_weekend_min,
        "schedule_matrix": normalize_schedule(policy.schedule_matrix or "1" * SCHEDULE_LENGTH),
        "blocked_apps": policy.blocked_apps or "",
        "blocked_domains": policy.blocked_domains or "",
        "blocked_categories": policy.blocked_categories or "",
        "paused_until": iso(policy.paused_until) if is_paused(policy) else None,
        "adjustment_date": day.isoformat(),
        "adjustment_minutes": adjustment_minutes(db, policy.child_id, day),
        "lock_reason": lock.reason if lock else None,
        "has_pin": bool(policy.lock_password_hash),
        "updated_at": iso(policy.updated_at),
    }


def signed_policy(db: Session, policy: Policy, device_id: str, key: str) -> dict:
    payload = policy_payload(db, policy)
    payload.pop("has_pin", None)
    payload["device_id"] = device_id
    payload["issued_at"] = datetime.utcnow().isoformat() + "Z"
    return {"policy": payload, "signature": sign_payload(key, payload), "algorithm": "HMAC-SHA256"}
