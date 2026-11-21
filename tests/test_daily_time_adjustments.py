from contextlib import ExitStack
from datetime import datetime, timedelta
from unittest.mock import patch

from app import daily_time, services
from app.routers import child_portal, commands, policy_events


def frozen_clock(start):
    class Clock(datetime):
        current = start

        @classmethod
        def now(cls, tz=None):
            return cls.current

    return Clock


def patched(clock, *modules):
    stack = ExitStack()
    for module in modules:
        stack.enter_context(patch.object(module, "datetime", clock))
    return stack


def test_daily_adjustments_and_request_notifications(parent, portal):
    clock = frozen_clock(datetime(2040, 1, 6, 10))
    cid = parent.child_id
    with patched(clock, daily_time, policy_events, services, child_portal):
        policy = parent.client.get(f"/policy/{cid}").json()
        initial_adjustment = policy["adjustment_minutes"]
        base = (policy["daily_quota_weekday_min"], policy["daily_quota_weekend_min"])
        before = parent.client.get(f"/web-usage/{cid}").json()["remaining_seconds"]
        with parent.client.websocket_connect("/ws/parent") as ws:
            created = portal.client.post("/api/child/time-requests", json={"requested_minutes": 15}).json()
            notice = ws.receive_json()
            assert notice["cmd"] == "new_time_request" and notice["request_id"] == created["request_id"]
            url = f"/requests/{created['request_id']}/approve"
            assert parent.client.post(url).is_success
            assert ws.receive_json()["cmd"] == "extend_time"
            assert parent.client.post(url).status_code == 409
            assert parent.client.get(f"/web-usage/{cid}").json()["remaining_seconds"] == before + 900
            assert parent.client.post("/policy/deduct-time", json={"child_id": cid, "deduct_min": 5}).is_success
            assert ws.receive_json()["cmd"] == "time_deducted"
            assert parent.client.post("/commands/send", json={"child_id": cid, "action": "extend_time", "duration_min": 10}).is_success
            assert ws.receive_json()["cmd"] == "extend_time"
        dashboard = parent.client.get(f"/dashboard-stats/{cid}").json()
        assert dashboard["remaining_seconds"] == portal.client.get("/api/child/web-usage").json()["remaining_seconds"]
        assert dashboard["remaining_seconds"] == before + 1200
        policy = parent.client.get(f"/policy/{cid}").json()
        assert (policy["daily_quota_weekday_min"], policy["daily_quota_weekend_min"]) == base
        assert policy["adjustment_minutes"] == initial_adjustment + 20
        clock.current += timedelta(days=1)
        assert parent.client.get(f"/web-usage/{cid}").json()["adjustment_minutes"] == 0


def test_stream_ends_when_child_stops_or_disconnects(parent, portal):
    with parent.client.websocket_connect("/ws/parent") as ws:
        with portal.client.websocket_connect("/ws/child") as child:
            for stop_explicitly in (True, False):
                child.send_json({"type": "consent_response", "approved": True})
                assert ws.receive_json()["approved"] is True
                if stop_explicitly:
                    child.send_json({"type": "stop_screen_share"})
                    assert ws.receive_json()["cmd"] == "screen_share_stopped"
        assert ws.receive_json()["cmd"] == "screen_share_stopped"


def test_agent_heartbeat_reports_quota_used_once(parent, agent):
    client, headers, _ = agent
    clock = frozen_clock(datetime(2040, 1, 9, 10))
    with patched(clock, commands, policy_events, services, child_portal):
        day = clock.current.date().isoformat()
        for seconds in (63, 63, 15):
            resp = client.post("/heartbeat", json={"usage_day": day, "quota_used": seconds}, headers=headers)
            assert resp.is_success and "server_epoch" in resp.json()
        stats = parent.client.get(f"/dashboard-stats/{parent.child_id}").json()
        assert stats["today_seconds"] >= 63
        clock.current += timedelta(days=1)
        assert parent.client.get(f"/web-usage/{parent.child_id}").json()["today_seconds"] == 0


def test_manual_lock_persists_across_child_reconnect(parent, portal):
    cid = parent.child_id
    lock = {"child_id": cid, "action": "lock_window", "reason": "QA lock"}
    assert parent.client.post("/commands/send", json=lock).is_success
    try:
        with portal.client.websocket_connect("/ws/child"):
            pass
        assert portal.client.get("/api/child/web-usage").json()["lock_reason"] == "QA lock"
        assert parent.client.post("/commands/send", json={"child_id": cid, "action": "extend_time", "duration_min": 5}).is_success
        assert parent.client.get(f"/web-usage/{cid}").json()["lock_reason"] == "QA lock"
    finally:
        assert parent.client.post("/commands/send", json={**lock, "action": "unlock_window"}).is_success
    assert parent.client.get(f"/web-usage/{cid}").json()["lock_reason"] is None
