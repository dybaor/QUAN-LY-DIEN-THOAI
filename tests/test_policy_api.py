"""Chính sách: lịch 7x48, tăng version, kiểm tra hợp lệ, không lộ mã PIN, whitelist mô phỏng ứng dụng."""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routers.policy_events import LaunchAppSchema, PolicyUpdateSchema, launch_desktop_app

BASE_DIR = Path(__file__).resolve().parent.parent


def test_policy_uses_336_slot_schedule_and_hides_pin(parent):
    policy = parent.client.get(f"/policy/{parent.child_id}").json()
    assert len(policy["schedule_matrix"]) == 336
    assert policy["has_pin"] is True
    assert "lock_pin" not in policy and "lock_password_hash" not in policy


def test_update_policy_expands_legacy_matrix_and_increments_version(parent):
    before = parent.client.get(f"/policy/{parent.child_id}").json()["version"]
    hourly = "1" * 24 * 5 + "0" * 24 * 2
    resp = parent.client.put("/policy/update", json={
        "child_id": parent.child_id, "daily_quota_weekday_min": 135, "daily_quota_weekend_min": 200,
        "schedule_matrix": hourly, "blocked_categories": "games,inappropriate",
    })
    assert resp.status_code == 200, resp.text
    policy = parent.client.get(f"/policy/{parent.child_id}").json()
    assert policy["version"] == before + 1
    assert policy["schedule_matrix"] == "1" * 48 * 5 + "0" * 48 * 2
    assert policy["blocked_categories"] == "games,inappropriate"
    assert policy["daily_quota_weekday_min"] == 135


def test_schedule_and_category_validation():
    base = {"child_id": 1, "daily_quota_weekday_min": 100, "daily_quota_weekend_min": 100}
    assert len(PolicyUpdateSchema(**base, schedule_matrix="10" * 168).schedule_matrix) == 336
    for bad in ("1" * 100, "1" * 335 + "2"):
        with pytest.raises(ValidationError):
            PolicyUpdateSchema(**base, schedule_matrix=bad)
    with pytest.raises(ValidationError):
        PolicyUpdateSchema(**base, blocked_categories="games,porn")


def test_launch_desktop_app_whitelist_security():
    with patch("subprocess.Popen") as popen:
        assert launch_desktop_app(LaunchAppSchema(app_id="calc"))["app_id"] == "calc"
        popen.assert_not_called()
    with pytest.raises(HTTPException) as ctx:
        launch_desktop_app(LaunchAppSchema(app_id="powershell.exe"))
    assert ctx.value.status_code == 400


def test_child_profile_update_and_pin_change(parent, portal):
    resp = parent.client.put(f"/api/children/{parent.child_id}", json={"name": "Bé Minh", "pin": "6789"})
    assert resp.status_code == 200 and resp.json()["name"] == "Bé Minh"
    assert portal.client.post("/api/child/verify-pin", json={"pin": "6789"}).json()["valid"] is True
    for wrong in ("1234", "0000", "9999"):
        assert portal.client.post("/api/child/verify-pin", json={"pin": wrong}).json()["valid"] is False
    parent.client.put(f"/api/children/{parent.child_id}", json={"name": "Bé An", "pin": "2468"})


def test_agent_never_touches_windows_ui_or_lock():
    """Agent chỉ ghi sự kiện: không khóa máy, không popup, không thao tác tắt/đăng xuất Windows."""
    forbidden = ("WTSSendMessageW", "LockWorkStation", "MessageBox", "ExitWindows", "shutdown /s", "shutdown /r",
                 "SwitchDesktop", "SetForegroundWindow", "ShowWindow(", "SendMessage(")
    for py_file in (BASE_DIR / "agent").glob("*.py"):
        if py_file.name == "safe_browser.py":
            continue  # Trình duyệt an toàn Tkinter cũ, không được Service nạp
        for number, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#")[0]
            if py_file.name == "tray_ui.py" and "SetForegroundWindow" in code:
                continue  # chỉ để menu khay đóng đúng cách, không động tới cửa sổ khác
            for word in forbidden:
                assert word not in code, f"{py_file.name}:{number}: {line.strip()}"
