"""Cấu hình Agent: địa chỉ máy chủ, ghim chứng chỉ, thư mục dữ liệu và các ngưỡng thời gian.

Thứ tự ưu tiên: biến môi trường > %ProgramData%\\OGKAgent\\agent_config.json > mặc định.
"""

import json
import os
from urllib.parse import urlsplit


def data_dir() -> str:
    base = os.environ.get("OGK_AGENT_DATA") or os.path.expandvars(r"%ProgramData%\OGKAgent")
    try:
        os.makedirs(base, exist_ok=True)
        probe = os.path.join(base, f".probe_{os.getpid()}")
        with open(probe, "w") as handle:
            handle.write("1")
        os.remove(probe)
        return base
    except OSError:
        fallback = os.path.abspath("./ogk_agent_data")
        os.makedirs(fallback, exist_ok=True)
        return fallback


DATA_DIR = data_dir()
CONFIG_PATH = os.path.join(DATA_DIR, "agent_config.json")


def _file_config() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


_cfg = _file_config()
SERVER_URL = (os.environ.get("OGK_SERVER_URL") or _cfg.get("server_url") or "http://127.0.0.1:8000").rstrip("/")
# SHA-256 (hex) của chứng chỉ DER máy chủ; khi đặt, mọi kết nối HTTPS/WSS phải khớp đúng chứng chỉ này.
CERT_SHA256 = (os.environ.get("OGK_CERT_SHA256") or _cfg.get("cert_sha256") or "").replace(":", "").lower()
CA_BUNDLE = os.environ.get("OGK_CA_BUNDLE") or _cfg.get("ca_bundle") or None

_parts = urlsplit(SERVER_URL)
IS_LOCAL = _parts.hostname in ("127.0.0.1", "localhost", "::1")
if _parts.scheme != "https" and not IS_LOCAL:
    raise RuntimeError("OGK_SERVER_URL phải dùng HTTPS khi máy chủ không nằm trên máy này.")
WS_URL = ("wss://" if _parts.scheme == "https" else "ws://") + _parts.netloc + "/ws/agent"

HEARTBEAT_INTERVAL_SEC = 60
CLOCK_SKEW_LIMIT_SEC = 120          # Lệch giờ so với máy chủ vượt ngưỡng → sự kiện clock_tamper
WARNING_MINUTES = (10, 5, 1)        # Cảnh báo trước khi hết giờ
GRACE_PERIOD_SEC = 60               # Ân hạn để trẻ lưu bài trước khi khóa
IDLE_THRESHOLD_SEC = 300
UI_MISSING_LIMIT_SEC = 120          # Không thấy giao diện khay hệ thống quá ngưỡng → tạm dừng giám sát
PIPE_NAME = r"\\.\pipe\OGKAgentUI"
