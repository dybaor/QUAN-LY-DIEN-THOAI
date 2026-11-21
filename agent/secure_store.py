"""Mã hóa AES-256-GCM cho dữ liệu nhạy cảm trong bộ nhớ đệm Agent (token, khóa ký chính sách).

Khóa AES được sinh ngẫu nhiên và lưu ở dạng đã bảo vệ bằng Windows DPAPI (phạm vi máy),
nên file cache sao chép sang máy khác không giải mã được. Có thể thay bằng biến môi trường OGK_AGENT_KEY.
"""

import base64
import os
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from settings import DATA_DIR

KEY_PATH = os.path.join(DATA_DIR, "cache.key")
_PREFIX = "enc:v1:"
CRYPTPROTECT_LOCAL_MACHINE = 0x4


def _dpapi_protect(data: bytes) -> bytes:
    import win32crypt
    return win32crypt.CryptProtectData(data, "OGKAgent", None, None, None, CRYPTPROTECT_LOCAL_MACHINE)


def _dpapi_unprotect(data: bytes) -> bytes:
    import win32crypt
    return win32crypt.CryptUnprotectData(data, None, None, None, CRYPTPROTECT_LOCAL_MACHINE)[1]


def _load_key() -> bytes:
    env_key = os.environ.get("OGK_AGENT_KEY")
    if env_key:
        key = base64.b64decode(env_key)
        if len(key) != 32:
            raise RuntimeError("OGK_AGENT_KEY phải là 32 byte mã hóa base64")
        return key
    if os.path.exists(KEY_PATH):
        with open(KEY_PATH, "rb") as handle:
            return _dpapi_unprotect(handle.read())
    key = AESGCM.generate_key(bit_length=256)
    with open(KEY_PATH, "wb") as handle:
        handle.write(_dpapi_protect(key))
    return key


_aes: Optional[AESGCM] = None


def _cipher() -> AESGCM:
    global _aes
    if _aes is None:
        _aes = AESGCM(_load_key())
    return _aes


def encrypt(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    nonce = os.urandom(12)
    return _PREFIX + base64.b64encode(nonce + _cipher().encrypt(nonce, value.encode("utf-8"), None)).decode()


def decrypt(value: Optional[str]) -> Optional[str]:
    if not value or not value.startswith(_PREFIX):
        return value
    raw = base64.b64decode(value[len(_PREFIX):])
    return _cipher().decrypt(raw[:12], raw[12:], None).decode("utf-8")
