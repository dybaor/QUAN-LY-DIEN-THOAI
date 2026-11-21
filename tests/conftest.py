"""Cấu hình chung: mọi bài test dùng thư mục dữ liệu tạm, không chạm vào ogk_system.db thật."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

_DATA = Path(tempfile.mkdtemp(prefix="ogk_test_"))
os.environ["OGK_DATA_DIR"] = str(_DATA / "server")
os.environ["OGK_AGENT_DATA"] = str(_DATA / "agent")
os.environ["OGK_AGENT_CACHE"] = str(_DATA / "agent" / "agent_cache.db")
(_DATA / "server").mkdir(parents=True, exist_ok=True)
(_DATA / "agent").mkdir(parents=True, exist_ok=True)

ROOT = Path(__file__).resolve().parent.parent
for folder in (ROOT, ROOT / "server", ROOT / "agent", ROOT / "dns_proxy"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))


PARENT = {"username": "bame_test", "password": "matkhau-test-123"}
CHILD_PIN = "2468"


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from app.routers import auth
    auth.login_limiter.reset()
    auth.pin_limiter.reset()
    yield


def _client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


class Session:
    def __init__(self, client, data):
        self.client = client
        self.data = data
        self.child_id = data["children"][0]["id"] if data.get("children") else data.get("child_id")


@pytest.fixture
def parent():
    """Phụ huynh đã đăng nhập (tạo tài khoản ở lần đầu), kèm mã CSRF trong header."""
    with _client() as client:
        status = client.get("/api/auth/status").json()
        if status.get("has_account"):
            resp = client.post("/api/auth/login", json=PARENT)
        else:
            resp = client.post("/api/auth/register", json={**PARENT, "child_name": "Bé An", "child_age": 9, "pin": CHILD_PIN})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        client.headers["X-CSRF-Token"] = data["csrf_token"]
        yield Session(client, data)


def pairing_code(parent_session, child_id=None):
    resp = parent_session.client.post(f"/api/children/{child_id or parent_session.child_id}/pairing-code")
    assert resp.status_code == 200, resp.text
    return resp.json()["code"]


@pytest.fixture
def portal(parent):
    """Cổng học tập của trẻ đã ghép đôi bằng mã do phụ huynh tạo."""
    with _client() as client:
        resp = client.post("/api/child/pair", json={"code": pairing_code(parent)})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        client.headers["X-CSRF-Token"] = data["csrf_token"]
        yield Session(client, data)


@pytest.fixture
def agent(parent):
    """Thiết bị Agent đã ghép đôi: trả về (client, header Bearer, dữ liệu ghép đôi)."""
    import uuid
    with _client() as client:
        resp = client.post("/enroll/verify", json={"code": pairing_code(parent), "fingerprint": f"MACHINE-{uuid.uuid4()}"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        yield client, {"Authorization": f"Bearer {data['access_token']}"}, data
