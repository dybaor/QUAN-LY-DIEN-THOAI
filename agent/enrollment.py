"""Ghép đôi Agent với tài khoản phụ huynh bằng mã 8 ký tự (KT-2)."""

import socket

import requests

from local_cache import local_cache
from transport import api


def enroll(code: str, device_name: str = "") -> dict:
    """Gửi mã ghép đôi + fingerprint máy lên `/enroll/verify`, lưu device_id và token đã mã hóa vào cache."""
    payload = {
        "code": code.strip().upper(),
        "fingerprint": local_cache.fingerprint,
        "device_name": device_name or socket.gethostname(),
    }
    try:
        resp = api.post_public("/enroll/verify", payload)
    except requests.RequestException as exc:
        raise RuntimeError(f"Không kết nối được máy chủ OGK: {exc}") from exc
    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail")
        except ValueError:
            detail = resp.text
        raise RuntimeError(f"Ghép đôi thất bại: {detail}")
    data = resp.json()
    local_cache.save_identity(data["device_id"], data["child_id"], data["access_token"], data["refresh_token"],
                              data["policy_key"])
    return data
