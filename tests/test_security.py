"""Bảo mật & toàn vẹn theo báo cáo kiểm toán (F5-1..F5-5, F4-2, F4-3, F3-4, KT-2, KT-5)."""

import sqlite3
import uuid
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app import config
from app.database import SessionLocal
from app.main import app
from app.models import Child, Device, DeviceEvent, Parent, Policy
from app.routers.policy_events import purge_older_than
from app.security import hash_secret

from conftest import CHILD_PIN, PARENT


def make_other_parent():
    """Một phụ huynh khác cùng hệ thống (kiểm tra IDOR / khóa đăng nhập)."""
    username = f"khac_{uuid.uuid4().hex[:6]}"
    with SessionLocal() as db:
        other = Parent(username=username, hashed_password=hash_secret("mat-khau-khac-123"), role="parent")
        db.add(other)
        db.flush()
        child = Child(parent_id=other.id, name="Con nhà khác", age=8)
        db.add(child)
        db.flush()
        db.add(Policy(child_id=child.id, lock_password_hash=hash_secret("1357")))
        db.commit()
        return username, child.id


def test_endpoints_require_authentication():
    with TestClient(app) as anonymous:
        for path in ("/policy/1", "/dashboard-stats/1", "/reports/summary/1", "/requests/", "/api/child/policy"):
            assert anonymous.get(path).status_code == 401, path
        assert anonymous.post("/events/batch", json=[]).status_code == 401
        assert anonymous.post("/heartbeat", json={}).status_code == 401
        assert anonymous.get("/api/auth/status").json()["authenticated"] is False


def test_csrf_token_required_for_writes(parent):
    payload = {"child_id": parent.child_id, "daily_quota_weekday_min": 120, "daily_quota_weekend_min": 180}
    token = parent.client.headers.pop("X-CSRF-Token")
    try:
        assert parent.client.put("/policy/update", json=payload).status_code == 403
        assert parent.client.put("/policy/update", json=payload, headers={"X-CSRF-Token": "sai"}).status_code == 403
        assert parent.client.put("/policy/update", json=payload, headers={"X-CSRF-Token": token,
                                 "Origin": "http://evil.example"}).status_code == 403
    finally:
        parent.client.headers["X-CSRF-Token"] = token
    assert parent.client.put("/policy/update", json=payload).status_code == 200


def test_secrets_are_hashed_and_encrypted_at_rest(parent):
    raw = sqlite3.connect(config.DB_PATH)
    password, = raw.execute("SELECT hashed_password FROM parents WHERE username = ?", (PARENT["username"],)).fetchone()
    pin_hash, = raw.execute("SELECT lock_password_hash FROM policies WHERE child_id = ?", (parent.child_id,)).fetchone()
    name, = raw.execute("SELECT name FROM children WHERE id = ?", (parent.child_id,)).fetchone()
    raw.close()
    assert password.startswith("$argon2id$") and pin_hash.startswith("$argon2id$")
    assert name.startswith("enc:v1:") and "An" not in name


def test_register_rejected_once_account_exists(parent):
    resp = parent.client.post("/api/auth/register", json={**PARENT, "child_name": "X", "pin": "1234"})
    assert resp.status_code == 409


def test_login_lockout_after_five_failures():
    username, _ = make_other_parent()
    with TestClient(app) as client:
        for _ in range(config.MAX_FAILED_LOGINS):
            assert client.post("/api/auth/login", json={"username": username, "password": "sai-mat-khau-1"}).status_code == 401
        locked = client.post("/api/auth/login", json={"username": username, "password": "mat-khau-khac-123"})
        assert locked.status_code == 423


def test_idor_other_parent_cannot_read_or_modify_child(parent):
    username, other_child = make_other_parent()
    with TestClient(app) as other:
        data = other.post("/api/auth/login", json={"username": username, "password": "mat-khau-khac-123"}).json()
        other.headers["X-CSRF-Token"] = data["csrf_token"]
        assert [c["id"] for c in data["children"]] == [other_child]
        assert other.get(f"/policy/{parent.child_id}").status_code == 404
        assert other.get(f"/reports/audit-log/{parent.child_id}").status_code == 404
        assert other.post("/commands/send", json={"child_id": parent.child_id, "action": "lock_window"}).status_code == 404
        assert other.delete(f"/data/purge-child/{parent.child_id}").status_code == 404
    assert parent.client.get(f"/policy/{other_child}").status_code == 404


def test_pin_lockout_and_audit_visible_to_child(parent, portal):
    for _ in range(config.MAX_FAILED_LOGINS):
        assert portal.client.post("/api/child/verify-pin", json={"pin": "0000"}).json()["valid"] is False
    assert portal.client.post("/api/child/verify-pin", json={"pin": CHILD_PIN}).status_code == 423
    with SessionLocal() as db:
        db.query(Policy).filter(Policy.child_id == parent.child_id).update({Policy.pin_locked_until: None})
        db.commit()
    assert portal.client.post("/api/child/verify-pin", json={"pin": CHILD_PIN}).json()["valid"] is True

    parent.client.put("/policy/update", json={"child_id": parent.child_id, "daily_quota_weekday_min": 95,
                                             "daily_quota_weekend_min": 180})
    parent_log = parent.client.get(f"/reports/audit-log/{parent.child_id}").json()
    entry = next(e for e in parent_log if e["action"] == "policy_updated")
    assert entry["client_ip"] and "95" in entry["new_value"] and entry["old_value"]
    child_log = portal.client.get("/api/child/audit-log").json()
    assert any(e["action"] == "pin_locked" for e in child_log)
    assert all("client_ip" not in e for e in child_log)


def test_agent_tokens_rotate_and_signed_policy(parent, agent):
    from ws_client import verify_policy_signature

    client, headers, enrolled = agent
    assert enrolled["child_id"] == parent.child_id
    envelope = client.get("/agent/policy", headers=headers).json()
    policy = verify_policy_signature(envelope, enrolled["policy_key"], enrolled["device_id"])
    assert policy and policy["child_id"] == parent.child_id
    tampered = {**envelope, "policy": {**envelope["policy"], "daily_quota_weekday_min": 1440}}
    assert verify_policy_signature(tampered, enrolled["policy_key"], enrolled["device_id"]) is None
    assert verify_policy_signature(envelope, "khoa-gia", enrolled["device_id"]) is None

    rotated = client.post("/enroll/refresh", json={"refresh_token": enrolled["refresh_token"]})
    assert rotated.status_code == 200
    assert client.post("/enroll/refresh", json={"refresh_token": enrolled["refresh_token"]}).status_code == 401


def test_event_ingestion_is_idempotent_and_validates_types(parent, agent):
    client, headers, _ = agent
    event = {"ts": datetime.utcnow().isoformat(), "type": "app_stop", "subject": "minecraft.exe",
             "duration_sec": 600, "idempotency_key": uuid.uuid4().hex}
    first = client.post("/events/batch", json=[event, event], headers=headers).json()
    assert (first["recorded_count"], first["duplicate_count"]) == (1, 1)
    again = client.post("/events/batch", json=[event], headers=headers).json()
    assert again["duplicate_count"] == 1
    mixed = client.post("/events/batch", headers=headers, json=[
        {**event, "type": "web_visit", "subject": "vnexpress.net", "idempotency_key": uuid.uuid4().hex},
        {**event, "type": "keylogger", "idempotency_key": uuid.uuid4().hex},
        {**event, "type": "clock_tamper", "subject": "lùi 300 giây", "idempotency_key": uuid.uuid4().hex},
    ]).json()
    assert (mixed["recorded_count"], mixed["rejected_count"]) == (2, 1)
    summary = parent.client.get(f"/reports/summary/{parent.child_id}?days=1").json()
    assert summary["top_apps"][0]["name"] == "minecraft.exe"
    assert any(row["domain"] == "vnexpress.net" for row in summary["top_domains"])
    assert any(e["action"] == "clock_tamper" for e in parent.client.get(f"/reports/audit-log/{parent.child_id}").json())
    csv = parent.client.get(f"/reports/export/{parent.child_id}.csv?days=7")
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv") and "minecraft.exe" in csv.text


def test_purge_notifies_agent_and_retention_cleans_old_rows(parent, agent):
    client, headers, enrolled = agent
    with client.websocket_connect("/ws/agent", headers=headers) as ws:
        assert parent.client.delete(f"/data/purge-child/{parent.child_id}").status_code == 200
        assert ws.receive_json()["cmd"] == "purge_cache"
    with SessionLocal() as db:
        db.add(DeviceEvent(ts=datetime.utcnow() - timedelta(days=91), device_id=enrolled["device_id"],
                           child_id=parent.child_id, type="app_start", subject="cũ"))
        db.commit()
        assert purge_older_than(db) >= 1
        assert db.query(DeviceEvent).filter(DeviceEvent.subject == "cũ").count() == 0


def test_parent_pause_stops_counting(parent, portal):
    assert parent.client.post("/policy/pause", json={"child_id": parent.child_id, "minutes": 30}).status_code == 200
    usage = portal.client.post("/api/child/web-usage").json()
    assert usage["paused"] is True and usage["paused_until"]
    assert portal.client.get("/api/child/policy").json()["paused_until"]
    assert parent.client.delete(f"/policy/pause/{parent.child_id}").status_code == 200
    assert portal.client.get("/api/child/web-usage").json()["paused"] is False


def test_uninstall_requires_parent_password(parent, agent):
    client, headers, enrolled = agent
    bad = client.post("/enroll/uninstall-authorize", json={"username": PARENT["username"], "password": "sai"}, headers=headers)
    assert bad.status_code == 401
    ok = client.post("/enroll/uninstall-authorize", json=PARENT, headers=headers)
    assert ok.status_code == 200
    assert client.post("/heartbeat", json={}, headers=headers).status_code == 401
    with SessionLocal() as db:
        assert db.get(Device, enrolled["device_id"]).is_active is False


def test_today_activity_for_child(portal, agent):
    client, headers, _ = agent
    client.post("/events/batch", headers=headers, json=[{"ts": datetime.utcnow().isoformat(), "type": "app_stop",
                "subject": "scratch.exe", "duration_sec": 300, "idempotency_key": uuid.uuid4().hex}])
    today = portal.client.get("/api/child/today").json()
    assert any(app["name"] == "scratch.exe" and app["minutes"] == 5 for app in today["apps"])
    assert {"used_minutes", "quota_minutes", "websites"} <= today.keys()
