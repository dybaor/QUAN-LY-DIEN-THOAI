"""Kênh truyền Agent ↔ Server: TLS 1.2+, ghim chứng chỉ (certificate pinning) và Bearer token tự làm mới."""

import hashlib
import ssl
import threading
from typing import Optional

import requests
from requests.adapters import HTTPAdapter

import settings
from local_cache import local_cache


class PinnedTLSAdapter(HTTPAdapter):
    """Bắt buộc TLS ≥ 1.2; nếu cấu hình CERT_SHA256 thì urllib3 so khớp vân tay chứng chỉ máy chủ."""

    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context(cafile=settings.CA_BUNDLE)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        if settings.CERT_SHA256:
            context.check_hostname = False   # Đã ghim chính xác chứng chỉ nên không phụ thuộc CA/tên miền
            context.verify_mode = ssl.CERT_NONE
            kwargs["assert_fingerprint"] = settings.CERT_SHA256
        kwargs["ssl_context"] = context
        return super().init_poolmanager(*args, **kwargs)


def websocket_ssl_context() -> Optional[ssl.SSLContext]:
    if not settings.WS_URL.startswith("wss://"):
        return None
    context = ssl.create_default_context(cafile=settings.CA_BUNDLE)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    if settings.CERT_SHA256:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


def certificate_matches(websocket) -> bool:
    """Kiểm tra vân tay chứng chỉ của kết nối WSS vừa mở (ghim chứng chỉ cho kênh lệnh khẩn)."""
    if not settings.CERT_SHA256 or not settings.WS_URL.startswith("wss://"):
        return True
    ssl_object = websocket.transport.get_extra_info("ssl_object")
    der = ssl_object.getpeercert(binary_form=True) if ssl_object else None
    return bool(der) and hashlib.sha256(der).hexdigest() == settings.CERT_SHA256


class AuthError(Exception):
    """Thiết bị chưa ghép đôi hoặc đã bị phụ huynh gỡ ghép đôi."""


class ApiClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.mount("https://", PinnedTLSAdapter())
        self._refresh_lock = threading.Lock()

    def url(self, path: str) -> str:
        return settings.SERVER_URL + path

    def auth_header(self) -> dict:
        token = local_cache.get_secret("access_token")
        return {"Authorization": f"Bearer {token}"} if token else {}

    def refresh(self) -> bool:
        with self._refresh_lock:
            refresh_token = local_cache.get_secret("refresh_token")
            if not refresh_token:
                return False
            resp = self.session.post(self.url("/enroll/refresh"), json={"refresh_token": refresh_token}, timeout=8)
            if resp.status_code != 200:
                return False
            data = resp.json()
            local_cache.set_secret("access_token", data["access_token"])
            local_cache.set_secret("refresh_token", data["refresh_token"])
            return True

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        if not local_cache.get_secret("access_token"):
            raise AuthError("Thiết bị chưa được ghép đôi")
        kwargs.setdefault("timeout", 8)
        resp = self.session.request(method, self.url(path), headers=self.auth_header(), **kwargs)
        if resp.status_code == 401:
            if not self.refresh():
                raise AuthError("Token không còn hợp lệ — cần ghép đôi lại")
            resp = self.session.request(method, self.url(path), headers=self.auth_header(), **kwargs)
        return resp

    def post_public(self, path: str, payload: dict) -> requests.Response:
        return self.session.post(self.url(path), json=payload, timeout=10)


api = ApiClient()
