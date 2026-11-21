"""Lõi Agent: cảnh báo 10/5/1 phút, ân hạn 60 giây, ghi sự kiện khóa (không đụng Windows), lịch 7x48, đếm giờ, hàng đợi chống trùng."""

import datetime
from unittest.mock import MagicMock

import pytest

from enforcer import TimeEnforcer, expand_schedule, seconds_until_blocked
from local_cache import LocalCache
from tracker import ScreenTimeTracker

MONDAY_10AM = datetime.datetime(2040, 1, 2, 10, 0, 0)  # Thứ Hai


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make_enforcer():
    blocker = MagicMock()
    events = []
    clock = FakeClock()
    enforcer = TimeEnforcer(blocker, lambda *args: events.append(args), clock=clock)
    return enforcer, blocker, events, clock


def policy(**overrides):
    base = {"id": 7, "daily_quota_weekday_min": 60, "daily_quota_weekend_min": 120, "schedule_matrix": "1" * 336,
            "adjustment_date": None, "adjustment_minutes": 0, "paused_until": None, "lock_reason": None}
    return {**base, **overrides}


def test_schedule_helpers_use_30_minute_slots():
    assert expand_schedule("10" * 84) == "1100" * 84
    matrix = "1" * 336
    matrix = matrix[:21] + "0" + matrix[22:]  # Thứ Hai 10:30–11:00 là giờ nghỉ
    assert seconds_until_blocked(matrix, MONDAY_10AM) == 1800
    assert seconds_until_blocked(matrix, MONDAY_10AM.replace(minute=40)) == 0
    assert seconds_until_blocked("1" * 336, MONDAY_10AM) > 86400


def test_warnings_then_grace_then_lock_event_only():
    enforcer, blocker, events, clock = make_enforcer()
    p = policy()
    for used, expected in ((50 * 60, 1), (55 * 60, 2), (59 * 60, 3)):
        enforcer.evaluate(p, used, MONDAY_10AM)
        assert len([e for e in events if e[0] == "quota_warning"]) == expected
    enforcer.evaluate(p, 59 * 60 + 30, MONDAY_10AM)
    assert len(events) == 3, "Không cảnh báo lặp lại cùng một mốc"

    state = enforcer.evaluate(p, 60 * 60, MONDAY_10AM)
    assert state["state"] == "grace" and not blocker.enforce_lock.called
    clock.now += 59
    assert enforcer.evaluate(p, 60 * 60, MONDAY_10AM)["state"] == "grace"
    clock.now += 2
    assert enforcer.evaluate(p, 60 * 60, MONDAY_10AM)["state"] == "locked"
    blocker.enforce_lock.assert_called_once()
    # Trẻ vẫn dùng tiếp: không ghi trùng sự kiện, không có thao tác nào khác
    clock.now += 120
    enforcer.evaluate(p, 61 * 60, MONDAY_10AM)
    blocker.enforce_lock.assert_called_once()


def test_extension_cancels_lock_and_rearms_warnings():
    enforcer, blocker, events, clock = make_enforcer()
    enforcer.evaluate(policy(), 59 * 60, MONDAY_10AM)
    extended = policy(adjustment_date=MONDAY_10AM.date().isoformat(), adjustment_minutes=30)
    assert enforcer.evaluate(extended, 59 * 60, MONDAY_10AM)["state"] == "active"
    enforcer.evaluate(extended, 80 * 60, MONDAY_10AM)
    assert sum(1 for e in events if e[0] == "quota_warning") >= 2


def test_login_after_quota_locks_immediately_and_pause_suspends():
    enforcer, blocker, _, _ = make_enforcer()
    assert enforcer.evaluate(policy(), 61 * 60, MONDAY_10AM)["state"] == "locked"
    paused_until = (datetime.datetime.utcnow() + datetime.timedelta(hours=1)).isoformat() + "Z"
    other, other_blocker, _, _ = make_enforcer()
    assert other.evaluate(policy(paused_until=paused_until), 61 * 60, MONDAY_10AM)["state"] == "paused"
    other_blocker.enforce_lock.assert_not_called()


def test_parent_lock_is_immediate():
    enforcer, blocker, _, _ = make_enforcer()
    enforcer.manual_lock = "Đi ăn cơm"
    assert enforcer.evaluate(policy(), 0, MONDAY_10AM)["state"] == "locked"
    assert "Đi ăn cơm" in blocker.enforce_lock.call_args.args[0]


@pytest.fixture
def cache(tmp_path, monkeypatch):
    store = LocalCache(db_path=str(tmp_path / "agent_cache.db"))
    monkeypatch.setattr("tracker.local_cache", store)
    return store


def test_tracker_excludes_locked_screen_and_idle(cache):
    tracker = ScreenTimeTracker()
    active = {"idle_sec": 1, "fg_name": "notepad.exe", "locked": False}
    tracker.last_monotonic -= 1
    assert tracker.tick(active)[0] == 1
    tracker.last_monotonic -= 1
    assert tracker.tick({**active, "locked": True}) == (0.0, True)
    tracker.last_monotonic -= 1
    assert tracker.tick({**active, "idle_sec": 400}) == (0.0, True)
    assert tracker.tick(None) == (0.0, True)
    assert cache.get_today_usage_seconds() == 1


def test_server_time_skew_reported_once(cache):
    tracker = ScreenTimeTracker()
    assert tracker.check_server_time(1000.0, 1300.0, 1300.2) is not None
    assert tracker.check_server_time(1000.0, 1300.0, 1300.2) is not None
    assert [e["type"] for e in cache.peek_events()] == ["clock_tamper"]
    assert tracker.check_server_time(1300.0, 1300.0, 1300.2) is None


def test_cache_identity_encryption_idempotency_and_purge(cache):
    cache.save_identity("dev-1", 5, "access-secret", "refresh-secret", "policy-key")
    assert cache.is_enrolled and cache.device_id == "dev-1" and cache.child_id == 5
    assert cache.get_value("access_token").startswith("enc:v1:")
    assert cache.get_secret("access_token") == "access-secret"
    cache.enqueue_event("app_start", "a.exe")
    cache.enqueue_event("app_start", "a.exe")
    keys = [e["idempotency_key"] for e in cache.peek_events()]
    assert len(set(keys)) == 2 and all(len(k) == 32 for k in keys)
    cache.add_daily_usage(120)
    cache.purge_activity()
    assert cache.get_pending_event_count() == 0
    assert cache.get_today_usage_seconds() == 120
