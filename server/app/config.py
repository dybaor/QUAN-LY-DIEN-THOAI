"""Cấu hình runtime của OGK Server (đường dẫn dữ liệu, khóa bí mật, tham số bảo mật).

Mọi giá trị nhạy cảm đọc từ biến môi trường; nếu thiếu, server tự sinh và lưu vào
`ogk_secrets.json` cạnh cơ sở dữ liệu (file này không được commit).
"""

import base64
import json
import os
import secrets
import sys
from pathlib import Path


def _default_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


DATA_DIR = Path(os.environ.get("OGK_DATA_DIR") or _default_data_dir())
DB_PATH = Path(os.environ.get("OGK_DB_PATH") or DATA_DIR / "ogk_system.db")
SECRETS_PATH = Path(os.environ.get("OGK_SECRETS_PATH") or DB_PATH.with_name("ogk_secrets.json"))

# Phiên đăng nhập & xác thực
SESSION_COOKIE = "ogk_session"
CHILD_SESSION_COOKIE = "ogk_child"
SESSION_HOURS = 12
CHILD_SESSION_DAYS = 30
ACCESS_TOKEN_MINUTES = 15
REFRESH_TOKEN_DAYS = 30
PASSWORD_MIN_LENGTH = 10
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15
LOGIN_RATE_PER_MINUTE = 20          # Số yêu cầu đăng nhập tối đa / IP / phút
COOKIE_SECURE = os.environ.get("OGK_COOKIE_SECURE", "").lower() in ("1", "true", "yes")

# Vòng đời dữ liệu (F3-4)
RETENTION_DAYS = 90
RETENTION_INTERVAL_SEC = 6 * 3600

# Giao thức Agent
HEARTBEAT_INTERVAL_SEC = 60
PAUSE_MAX_MINUTES = 120


def _load_secrets() -> dict:
    data = {}
    if SECRETS_PATH.exists():
        try:
            data = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
    changed = False
    if not data.get("jwt_secret"):
        data["jwt_secret"] = secrets.token_urlsafe(48)
        changed = True
    if not data.get("data_key"):
        data["data_key"] = base64.b64encode(secrets.token_bytes(32)).decode()
        changed = True
    if changed:
        SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SECRETS_PATH.write_text(json.dumps(data), encoding="utf-8")
        try:
            os.chmod(SECRETS_PATH, 0o600)
        except OSError:
            pass
    return data


_secrets = _load_secrets()
JWT_SECRET = os.environ.get("OGK_JWT_SECRET") or _secrets["jwt_secret"]
DATA_KEY = base64.b64decode(os.environ.get("OGK_DATA_KEY") or _secrets["data_key"])
if len(DATA_KEY) != 32:
    raise RuntimeError("OGK_DATA_KEY phải là 32 byte mã hóa base64 (AES-256-GCM).")
