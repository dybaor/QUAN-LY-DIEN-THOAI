"""Mô phỏng một Agent để kiểm tra tích hợp với máy chủ đang chạy.

Cách dùng: python server/simulate_agent.py <tên-đăng-nhập-phụ-huynh> <mật-khẩu>
Các bước: đăng nhập phụ huynh → tạo mã ghép đôi → Agent ghép đôi → heartbeat → lấy chính sách có chữ ký → gửi sự kiện.
"""

import hashlib
import hmac
import json
import sys
import uuid
from datetime import datetime

import requests

SERVER_URL = "http://127.0.0.1:8000"


def main(username: str, password: str):
    parent = requests.Session()
    login = parent.post(f"{SERVER_URL}/api/auth/login", json={"username": username, "password": password})
    login.raise_for_status()
    csrf = login.json()["csrf_token"]
    child_id = login.json()["children"][0]["id"]
    code = parent.post(f"{SERVER_URL}/api/children/{child_id}/pairing-code", headers={"X-CSRF-Token": csrf}).json()["code"]
    print(f"✓ Mã ghép đôi: {code}")

    enrolled = requests.post(f"{SERVER_URL}/enroll/verify", json={
        "code": code, "fingerprint": f"SIM-{uuid.uuid4()}", "device_name": "Máy mô phỏng"}).json()
    headers = {"Authorization": f"Bearer {enrolled['access_token']}"}
    print(f"✓ Ghép đôi thành công: device_id={enrolled['device_id']}")

    beat = requests.post(f"{SERVER_URL}/heartbeat", headers=headers, json={
        "usage_day": datetime.now().date().isoformat(), "quota_used": 600}).json()
    print(f"✓ Heartbeat: phiên bản chính sách {beat['latest_version']}, giờ máy chủ {beat['server_time']}")

    envelope = requests.get(f"{SERVER_URL}/agent/policy", headers=headers).json()
    canonical = json.dumps(envelope["policy"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    expected = hmac.new(enrolled["policy_key"].encode(), canonical, hashlib.sha256).hexdigest()
    print(f"✓ Chữ ký chính sách hợp lệ: {hmac.compare_digest(expected, envelope['signature'])}")

    events = [{"ts": datetime.utcnow().isoformat(), "type": t, "subject": s, "duration_sec": d,
               "idempotency_key": uuid.uuid4().hex}
              for t, s, d in (("app_start", "scratch.exe", 0), ("app_stop", "scratch.exe", 900),
                              ("blocked_domain", "facebook.com", 0))]
    print("✓ Gửi sự kiện:", requests.post(f"{SERVER_URL}/events/batch", headers=headers, json=events).json())


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
