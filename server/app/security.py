"""Tiện ích bảo mật: băm Argon2id, mã hóa AES-256-GCM, chữ ký HMAC chính sách và JWT cho Agent."""

import base64
import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional, Tuple

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jose import JWTError, jwt
from sqlalchemy.types import String, TypeDecorator

from . import config

_hasher = PasswordHasher()  # Argon2id, tham số mặc định của argon2-cffi (RFC 9106 low-memory)
_aes = AESGCM(config.DATA_KEY)
_ENC_PREFIX = "enc:v1:"
JWT_ALGORITHM = "HS256"


# ---------- Argon2id ----------
def hash_secret(value: str) -> str:
    return _hasher.hash(value)


def verify_secret(stored: Optional[str], value: str) -> Tuple[bool, bool]:
    """Trả về (hợp lệ, cần băm lại). Hỗ trợ đọc mã SHA-256 cũ để nâng cấp dần sang Argon2id."""
    if not stored or not value:
        return False, False
    if stored.startswith("$argon2"):
        try:
            _hasher.verify(stored, value)
            return True, _hasher.check_needs_rehash(stored)
        except (VerificationError, InvalidHashError):
            return False, False
    legacy = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return hmac.compare_digest(stored, legacy), True


# ---------- AES-256-GCM cho trường nhạy cảm ----------
def encrypt_text(value: Optional[str]) -> Optional[str]:
    if value is None or value.startswith(_ENC_PREFIX):
        return value
    nonce = os.urandom(12)
    sealed = _aes.encrypt(nonce, value.encode("utf-8"), None)
    return _ENC_PREFIX + base64.b64encode(nonce + sealed).decode()


def decrypt_text(value: Optional[str]) -> Optional[str]:
    if value is None or not value.startswith(_ENC_PREFIX):
        return value  # Dữ liệu cũ chưa mã hóa, sẽ được mã hóa lại ở lần ghi kế tiếp
    raw = base64.b64decode(value[len(_ENC_PREFIX):])
    return _aes.decrypt(raw[:12], raw[12:], None).decode("utf-8")


class EncryptedString(TypeDecorator):
    """Cột chuỗi được mã hóa AES-GCM trong SQLite, giải mã trong suốt khi đọc."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt_text(value)

    def process_result_value(self, value, dialect):
        return decrypt_text(value)


# ---------- Token ngẫu nhiên ----------
def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_equals(a: Optional[str], b: Optional[str]) -> bool:
    return bool(a) and bool(b) and hmac.compare_digest(a, b)


# ---------- Chữ ký toàn vẹn chính sách (F4-2) ----------
def canonical_json(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def sign_payload(key: str, payload: dict) -> str:
    return hmac.new(key.encode("utf-8"), canonical_json(payload), hashlib.sha256).hexdigest()


# ---------- JWT cho Agent (access 15 phút + refresh 30 ngày) ----------
def _encode(device_id: str, kind: str, lifetime: timedelta) -> Tuple[str, str, datetime]:
    jti = uuid.uuid4().hex
    expires = datetime.utcnow() + lifetime
    token = jwt.encode({"sub": device_id, "type": kind, "jti": jti, "exp": expires}, config.JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, jti, expires


def create_token_pair(device_id: str) -> dict:
    access, access_jti, _ = _encode(device_id, "access", timedelta(minutes=config.ACCESS_TOKEN_MINUTES))
    refresh, refresh_jti, refresh_exp = _encode(device_id, "refresh", timedelta(days=config.REFRESH_TOKEN_DAYS))
    return {
        "access_token": access,
        "refresh_token": refresh,
        "access_jti": access_jti,
        "refresh_jti": refresh_jti,
        "refresh_expires": refresh_exp,
        "token_type": "bearer",
        "expires_in": config.ACCESS_TOKEN_MINUTES * 60,
    }


def decode_token(token: str, kind: str) -> Optional[dict]:
    try:
        claims = jwt.decode(token, config.JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None
    if claims.get("type") != kind or not claims.get("sub") or not claims.get("jti"):
        return None
    return claims
