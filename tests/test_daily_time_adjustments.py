from datetime import datetime, timedelta
from pathlib import Path
import sys
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from app.main import app
from app import daily_time
from app.routers import policy_events


def test_daily_adjustments_and_request_notifications():
    class Clock(datetime):
        current = datetime(2040, 1, 6, 10)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    with TestClient(app) as client, patch.object(daily_time, "datetime", Clock), patch.object(policy_events, "datetime", Clock):
        policy = client.get("/policy/1").json()
        initial_adjustment = policy["adjustment_minutes"]
        base = (policy["daily_quota_weekday_min"], policy["daily_quota_weekend_min"])
        before = client.get("/web-usage/1").json()["remaining_seconds"]
        with client.websocket_connect("/ws/parent_qa") as parent:
            created = client.post("/requests/", json={"requested_minutes": 15}).json()
            notice = parent.receive_json()
            assert notice["cmd"] == "new_time_request"
            assert notice["request_id"] == created["request_id"]
            url = f"/requests/{created['request_id']}/approve"
            assert client.post(url).is_success
            assert parent.receive_json()["cmd"] == "extend_time"
            assert client.post(url).status_code == 409
            assert client.get("/web-usage/1").json()["remaining_seconds"] == before + 900
            assert client.post("/policy/deduct-time", json={"deduct_min": 5}).is_success
            assert parent.receive_json()["cmd"] == "time_deducted"
            assert client.post("/commands/send", json={
                "device_id": "CHILD-PC", "action": "extend_time", "duration_min": 10,
            }).is_success
            assert parent.receive_json()["cmd"] == "extend_time"
        dashboard = client.get("/dashboard-stats/1").json()
        assert dashboard["remaining_seconds"] == client.get("/web-usage/1").json()["remaining_seconds"]
        assert dashboard["remaining_seconds"] == before + 1200
        policy = client.get("/policy/1").json()
        assert (policy["daily_quota_weekday_min"], policy["daily_quota_weekend_min"]) == base
        assert policy["adjustment_minutes"] == initial_adjustment + 20
        Clock.current += timedelta(days=1)
        assert client.get("/web-usage/1").json()["adjustment_minutes"] == 0


def test_stream_ends_when_child_stops_or_disconnects():
    with TestClient(app) as client, client.websocket_connect("/ws/parent_qa") as parent:
        with client.websocket_connect("/ws/child/qa") as child:
            for stop_explicitly in (True, False):
                child.send_json({"type": "consent_response", "approved": True})
                assert parent.receive_json()["approved"] is True
                if stop_explicitly:
                    child.send_json({"type": "stop_screen_share"})
                    assert parent.receive_json()["cmd"] == "screen_share_stopped"
        assert parent.receive_json()["cmd"] == "screen_share_stopped"

def test_manual_lock_persists_across_child_reconnect():
    with TestClient(app) as client:
        lock = {"device_id": "auto", "action": "lock_window", "reason": "QA lock"}
        assert client.post("/commands/send", json=lock).is_success
        try:
            with client.websocket_connect("/ws/child/qa"):
                pass
            assert client.get("/web-usage/1").json()["lock_reason"] == "QA lock"
            assert client.post("/commands/send", json={
                "device_id": "auto", "action": "extend_time", "duration_min": 5,
            }).is_success
            assert client.get("/web-usage/1").json()["lock_reason"] == "QA lock"
        finally:
            assert client.post("/commands/send", json={**lock, "action": "unlock_window"}).is_success
        assert client.get("/web-usage/1").json()["lock_reason"] is None
