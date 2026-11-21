"""Cô lập giữa gia đình/trẻ, quyền chéo vai trò, và các lỗi đã tìm thấy khi kiểm thử toàn diện."""

import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.websocket_manager import ConnectionManager

from conftest import pairing_code
from test_security import make_other_parent


def fake_ws():
    ws = MagicMock()
    ws.send_json = AsyncMock()
    ws.send_bytes = AsyncMock()
    return ws


def test_manager_delivers_only_to_scoped_connections():
    mgr = ConnectionManager()
    mine, theirs, kid1, kid2 = fake_ws(), fake_ws(), fake_ws(), fake_ws()
    mgr.active_connections["parent_1_a"].add(mine); mgr.scopes["parent_1_a"] = {1}
    mgr.active_connections["parent_2_b"].add(theirs); mgr.scopes["parent_2_b"] = {2}
    mgr.active_connections["child_1_x"].add(kid1); mgr.scopes["child_1_x"] = {1}
    mgr.active_connections["child_2_y"].add(kid2); mgr.scopes["child_2_y"] = {2}
    asyncio.run(mgr.notify_child({"cmd": "lock_window"}, 1))
    asyncio.run(mgr.send_bytes_to_parents(b"frame", 1))
    mine.send_json.assert_awaited_once(); kid1.send_json.assert_awaited_once()
    mine.send_bytes.assert_awaited_once()
    for other in (theirs, kid2):
        other.send_json.assert_not_awaited(); other.send_bytes.assert_not_awaited()


def test_other_family_websocket_never_sees_our_commands(parent, portal):
    username, other_child = make_other_parent()
    with TestClient(app) as other:
        data = other.post("/api/auth/login", json={"username": username, "password": "mat-khau-khac-123"}).json()
        other.headers["X-CSRF-Token"] = data["csrf_token"]
        with other.websocket_connect("/ws/parent") as spy:
            assert parent.client.post("/commands/send", json={"child_id": parent.child_id, "action": "lock_window",
                                                              "reason": "bí mật"}).is_success
            assert parent.client.post("/commands/send", json={"child_id": parent.child_id, "action": "unlock_window"}).is_success
            portal.client.post("/api/child/time-requests", json={"requested_minutes": 5})
            # Nếu có rò rỉ thì thông điệp lạ sẽ đến trước phản hồi chat của chính gia đình kia
            spy.send_json({"action": "chat_message", "child_id": other_child, "text": "ping"})
            first = spy.receive_json()
            assert first["cmd"] == "chat_message" and first["text"] == "ping", first
            # Cũng không thể ra lệnh/chat vào trẻ của gia đình khác qua WebSocket
            spy.send_json({"action": "lock_window", "child_id": parent.child_id})
            spy.send_json({"action": "chat_message", "child_id": parent.child_id, "text": "xâm nhập"})
            spy.send_json({"action": "chat_message", "child_id": other_child, "text": "ping2"})
            assert spy.receive_json()["text"] == "ping2"
    assert parent.client.get(f"/web-usage/{parent.child_id}").json()["lock_reason"] is None


def test_roles_cannot_cross_over(parent, portal, agent):
    kid, (device, headers, _) = portal.client, agent
    parent_only = [("put", "/policy/update", {"child_id": 1, "daily_quota_weekday_min": 1, "daily_quota_weekend_min": 1}),
                   ("post", "/commands/send", {"child_id": 1, "action": "lock_window"}),
                   ("post", "/api/children", {"name": "X", "pin": "1234"}),
                   ("post", "/requests/1/approve", {}),
                   ("delete", f"/data/purge-child/{parent.child_id}", None),
                   ("post", "/policy/pause", {"child_id": 1, "minutes": 30})]
    for method, url, body in parent_only:
        for who, client, extra in (("trẻ", kid, {}), ("thiết bị", device, headers)):
            resp = getattr(client, method)(url, headers=extra, **({"json": body} if body is not None else {}))
            assert resp.status_code in (401, 403), f"{who} gọi được {method.upper()} {url}: {resp.status_code}"
    # Phụ huynh không dùng được API của trẻ / thiết bị
    assert parent.client.get("/api/child/policy").status_code == 401
    assert parent.client.post("/heartbeat", json={}).status_code == 401
    # Trẻ không tự duyệt yêu cầu của mình
    req = kid.post("/api/child/time-requests", json={"requested_minutes": 5}).json()["request_id"]
    assert kid.post(f"/requests/{req}/approve").status_code in (401, 403)


def test_log_tables_show_local_time_not_utc(parent, portal):
    portal.client.post("/api/child/access-log", json={"target_name": "khanacademy.org", "target_type": "Trang web", "status": "blocked"})
    shown = parent.client.get(f"/api/access-history/{parent.child_id}").json()[0]["ts"]
    shown_dt = datetime.strptime(shown, "%H:%M:%S %d/%m/%Y")
    assert abs((datetime.now() - shown_dt).total_seconds()) < 120, f"hiển thị {shown} nhưng giờ máy là {datetime.now()}"
    violation = parent.client.get(f"/events/violations/{parent.child_id}").json()[0]["ts"]
    assert abs((datetime.now() - datetime.strptime(violation, "%H:%M:%S %d/%m/%Y")).total_seconds()) < 120


def test_one_block_is_one_event_and_search_text_not_in_events(parent, portal):
    portal.client.post("/api/child/access-log", json={"target_name": "từ khóa riêng tư của trẻ", "target_type": "Tìm kiếm", "status": "blocked"})
    events = parent.client.get(f"/events/violations/{parent.child_id}").json()
    assert [e["subject"] for e in events].count("google.com") == 1
    assert not any("riêng tư" in e["subject"] for e in events)
    portal.client.post("/api/child/access-log", json={"target_name": "bài tập toán lớp 5", "target_type": "Tìm kiếm", "status": "allowed"})
    domains = parent.client.get(f"/reports/top-domains/{parent.child_id}?days=1").json()
    assert not any("toán" in d["domain"] for d in domains)


def test_agent_hidden_tray_is_reported_to_parent(parent, agent):
    client, headers, enrolled = agent
    client.post("/heartbeat", json={"ui_present": False}, headers=headers)
    me = parent.client.get("/api/auth/me").json()
    device = next(d for d in me["children"][0]["devices"] if d["id"] == enrolled["device_id"])
    assert device["ui_present"] is False
    audit = parent.client.get(f"/reports/audit-log/{parent.child_id}").json()
    assert any(e["action"] == "agent_ui_missing" for e in audit)
    client.post("/heartbeat", json={"ui_present": True}, headers=headers)
    assert any(e["action"] == "agent_ui_restored" for e in parent.client.get(f"/reports/audit-log/{parent.child_id}").json())


def test_schedule_blocks_portal_and_blocked_event_reaches_child(parent, portal, agent):
    """Ngoài lịch: máy chủ báo schedule_blocked, không tính giờ. Agent chặn app: trẻ nhận thông báo trong cổng web."""
    cid = parent.child_id
    parent.client.put("/policy/update", json={"child_id": cid, "daily_quota_weekday_min": 100, "daily_quota_weekend_min": 100,
                                              "schedule_matrix": "0" * 336})
    try:
        usage = portal.client.get("/api/child/web-usage").json()
        assert usage["schedule_blocked"] is True
        before = usage["today_seconds"]
        portal.client.post("/api/child/web-usage")
        assert portal.client.get("/api/child/web-usage").json()["today_seconds"] == before
        client, headers, _ = agent
        with portal.client.websocket_connect("/ws/child") as kid_ws:
            client.post("/events/batch", headers=headers, json=[{"ts": datetime.utcnow().isoformat(), "type": "blocked_app",
                                                                  "subject": "roblox.exe", "idempotency_key": uuid.uuid4().hex}])
            toast = kid_ws.receive_json()
            assert toast["cmd"] == "violation_toast" and "roblox.exe" in toast["message"]
        paused = parent.client.post("/policy/pause", json={"child_id": cid, "minutes": 30})
        assert paused.is_success and portal.client.get("/api/child/web-usage").json()["schedule_blocked"] is False
    finally:
        parent.client.delete(f"/policy/pause/{cid}")
        parent.client.put("/policy/update", json={"child_id": cid, "daily_quota_weekday_min": 120, "daily_quota_weekend_min": 180,
                                                  "schedule_matrix": "1" * 336})


def test_close_session_becomes_overlay_lock(parent, portal):
    cid = parent.child_id
    assert parent.client.post("/commands/send", json={"child_id": cid, "action": "close_session"}).is_success
    try:
        assert "kết thúc phiên" in portal.client.get("/api/child/web-usage").json()["lock_reason"]
    finally:
        parent.client.post("/commands/send", json={"child_id": cid, "action": "unlock_window"})


def test_agent_blocker_only_hashes_matching_size(tmp_path, monkeypatch):
    from blocker import ProcessBlocker
    blocker = ProcessBlocker()
    policy = {"blocked_apps": '[{"name":"A","hash":"%s","size":123}]' % ("a" * 64)}
    assert blocker.blocked_entries(policy) == {"a" * 64: 123}
    legacy = {"blocked_apps": ("b" * 64) + "," + ("c" * 64)}
    assert blocker.blocked_entries(legacy) == {"b" * 64: None, "c" * 64: None}
    hashed = []
    monkeypatch.setattr(blocker, "calculate_file_sha256", lambda path: hashed.append(path) or None)
    blocker.check_and_enforce(policy)  # chỉ băm file đúng kích thước 123 → không có tiến trình nào khớp
    assert hashed == []


def test_enroll_clears_stale_policy_cache(tmp_path):
    from local_cache import LocalCache
    cache = LocalCache(db_path=str(tmp_path / "c.db"))
    cache.save_identity("d1", 1, "a", "r", "k")
    cache.save_policy({"child_id": 1, "version": 50})
    cache.save_identity("d2", 1, "a2", "r2", "k2")
    assert cache.get_policy() is None, "chính sách version cũ làm Agent từ chối chính sách mới của máy chủ"
