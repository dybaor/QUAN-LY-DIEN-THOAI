"""
OGK-Agent Local Cache — SQLite chế độ WAL tại %ProgramData%\\OGKAgent\\agent_cache.db.

- Định danh thiết bị sau khi ghép đôi (device_id, child_id) và bí mật đã mã hóa AES-GCM (token, khóa ký).
- Bản sao chính sách đã xác thực chữ ký để hoạt động ngoại tuyến.
- Hàng đợi sự kiện 7 trường kèm idempotency_key (UUID) để máy chủ chống đếm trùng khi gửi bù.
- Bộ đếm thời gian sử dụng theo ngày.
"""

import datetime
import json
import os
import sqlite3
import sys
import threading
import uuid
import winreg
from typing import Any, Dict, List, Optional

import secure_store
from settings import DATA_DIR

for _stream in (sys.stdout, sys.stderr):
    if _stream and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

SECRET_KEYS = {"access_token", "refresh_token", "policy_key"}


def get_machine_guid() -> str:
    """MachineGuid của Windows dùng làm fingerprint thiết bị khi ghép đôi."""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            if guid:
                return str(guid).strip()
    except OSError:
        pass
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"OGK-{uuid.getnode()}"))


def get_cache_db_path() -> str:
    return os.path.join(DATA_DIR, "agent_cache.db")


class LocalCache:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_cache_db_path()
        self.fingerprint = get_machine_guid()
        self._lock = threading.Lock()
        self._init_db()

    # ---------- Kết nối & lược đồ ----------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            policy_cols = {row[1] for row in conn.execute("PRAGMA table_info(cached_policy)")}
            if policy_cols and "payload" not in policy_cols:
                conn.execute("DROP TABLE cached_policy")  # Lược đồ cũ; bản sao chính sách sẽ được tải lại
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_identity (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS cached_policy (
                    child_id INTEGER PRIMARY KEY, version INTEGER DEFAULT 1, payload TEXT NOT NULL, updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS event_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL, device_id TEXT NOT NULL, child_id INTEGER NOT NULL,
                    type TEXT NOT NULL, subject TEXT NOT NULL, duration_sec INTEGER DEFAULT 0,
                    policy_id INTEGER, retry_count INTEGER DEFAULT 0, idempotency_key TEXT
                );
                CREATE TABLE IF NOT EXISTS daily_usage (
                    usage_date TEXT PRIMARY KEY, used_seconds INTEGER DEFAULT 0, updated_at TEXT
                );
                """
            )
            queue_cols = {row[1] for row in conn.execute("PRAGMA table_info(event_queue)")}
            if "idempotency_key" not in queue_cols:
                conn.execute("ALTER TABLE event_queue ADD COLUMN idempotency_key TEXT")
            conn.execute("UPDATE event_queue SET idempotency_key = lower(hex(randomblob(16))) WHERE idempotency_key IS NULL")
            conn.commit()

    # ---------- Định danh & bí mật ----------
    def get_value(self, key: str) -> Optional[str]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT value FROM agent_identity WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_value(self, key: str, value: Optional[str]) -> None:
        with self._lock, self._connect() as conn:
            if value is None:
                conn.execute("DELETE FROM agent_identity WHERE key = ?", (key,))
            else:
                conn.execute("INSERT INTO agent_identity (key, value) VALUES (?, ?) "
                             "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
            conn.commit()

    def get_secret(self, key: str) -> Optional[str]:
        return secure_store.decrypt(self.get_value(key))

    def set_secret(self, key: str, value: Optional[str]) -> None:
        self.set_value(key, secure_store.encrypt(value) if value is not None else None)

    @property
    def device_id(self) -> str:
        return self.get_value("device_id") or self.fingerprint

    @property
    def child_id(self) -> Optional[int]:
        value = self.get_value("child_id")
        return int(value) if value else None

    @property
    def is_enrolled(self) -> bool:
        return bool(self.get_value("device_id") and self.get_secret("access_token"))

    def save_identity(self, device_id: str, child_id: int, access_token: str, refresh_token: str, policy_key: str):
        # Ghép đôi mới: bỏ chính sách cũ, nếu không cơ chế chống phát lại sẽ từ chối chính sách (version thấp hơn) của máy chủ mới
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM cached_policy")
            conn.commit()
        self.set_value("device_id", device_id)
        self.set_value("child_id", str(child_id))
        self.set_secret("access_token", access_token)
        self.set_secret("refresh_token", refresh_token)
        self.set_secret("policy_key", policy_key)

    def clear_identity(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM agent_identity")
            conn.execute("DELETE FROM cached_policy")
            conn.commit()

    # ---------- Chính sách ----------
    def save_policy(self, policy: Dict[str, Any]) -> bool:
        child_id = policy.get("child_id") or self.child_id or 1
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO cached_policy (child_id, version, payload, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(child_id) DO UPDATE SET version = excluded.version, payload = excluded.payload, "
                "updated_at = excluded.updated_at",
                (child_id, policy.get("version", 1), json.dumps(policy, ensure_ascii=False),
                 datetime.datetime.utcnow().isoformat()),
            )
            conn.commit()
        return True

    def get_policy(self, child_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        c_id = child_id or self.child_id
        with self._lock, self._connect() as conn:
            if c_id:
                row = conn.execute("SELECT payload FROM cached_policy WHERE child_id = ?", (c_id,)).fetchone()
            else:
                row = conn.execute("SELECT payload FROM cached_policy ORDER BY updated_at DESC LIMIT 1").fetchone()
        return json.loads(row[0]) if row else None

    # ---------- Hàng đợi sự kiện ----------
    def enqueue_event(self, event_type: str, subject: str, duration_sec: int = 0, policy_id: Optional[int] = None,
                      child_id: Optional[int] = None, ts: Optional[str] = None) -> bool:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO event_queue (ts, device_id, child_id, type, subject, duration_sec, policy_id, idempotency_key) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (ts or datetime.datetime.utcnow().isoformat(), self._device_id_unlocked(conn),
                 child_id or self._child_id_unlocked(conn) or 0, event_type, str(subject)[:255],
                 int(duration_sec), policy_id, uuid.uuid4().hex),
            )
            conn.commit()
        return True

    def _device_id_unlocked(self, conn) -> str:
        row = conn.execute("SELECT value FROM agent_identity WHERE key = 'device_id'").fetchone()
        return row[0] if row else self.fingerprint

    @staticmethod
    def _child_id_unlocked(conn) -> Optional[int]:
        row = conn.execute("SELECT value FROM agent_identity WHERE key = 'child_id'").fetchone()
        return int(row[0]) if row else None

    def peek_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM event_queue ORDER BY id ASC LIMIT ?", (limit,))]

    def delete_events(self, event_ids: List[int]) -> bool:
        if not event_ids:
            return True
        with self._lock, self._connect() as conn:
            conn.execute(f"DELETE FROM event_queue WHERE id IN ({','.join('?' for _ in event_ids)})", event_ids)
            conn.commit()
        return True

    def get_pending_event_count(self) -> int:
        with self._lock, self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM event_queue").fetchone()[0]

    # ---------- Thời gian sử dụng ----------
    def add_daily_usage(self, additional_seconds: int) -> int:
        today = datetime.date.today().isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO daily_usage (usage_date, used_seconds, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(usage_date) DO UPDATE SET used_seconds = used_seconds + excluded.used_seconds, "
                "updated_at = excluded.updated_at",
                (today, additional_seconds, datetime.datetime.utcnow().isoformat()),
            )
            conn.commit()
            row = conn.execute("SELECT used_seconds FROM daily_usage WHERE usage_date = ?", (today,)).fetchone()
        return row[0] if row else 0

    def get_today_usage_seconds(self, day: Optional[datetime.date] = None) -> int:
        key = (day or datetime.date.today()).isoformat()
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT used_seconds FROM daily_usage WHERE usage_date = ?", (key,)).fetchone()
        return row[0] if row else 0

    def purge_activity(self) -> None:
        """Lệnh xóa dữ liệu từ phụ huynh: xóa hàng đợi sự kiện và lịch sử sử dụng.

        Giữ bộ đếm của hôm nay để hạn mức trong ngày vẫn được thực thi chính xác.
        """
        today = datetime.date.today().isoformat()
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM event_queue")
            conn.execute("DELETE FROM daily_usage WHERE usage_date <> ?", (today,))
            conn.commit()
            conn.execute("VACUUM")


local_cache = LocalCache()
