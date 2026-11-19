"""
OGK-Agent Local Cache Module (Thành viên A - SQLite Cục bộ)
Lưu trữ bản sao chính sách (Policy) và hàng đợi sự kiện (Event Queue)
tại %ProgramData%\\OGKAgent\\agent_cache.db theo chuẩn ACID và chế độ WAL mode.
"""

import datetime
import os
import platform
import sqlite3
import sys
import threading
import uuid
import winreg
from typing import Any, Dict, List, Optional

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def get_machine_guid() -> str:
    """Lấy MachineGuid duy nhất từ Registry hoặc fallback UUID."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            if guid:
                return str(guid).strip()
    except Exception:
        pass
    node = uuid.getnode()
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"OGK-{node}"))


def get_cache_db_path() -> str:
    """Lấy đường dẫn DB cache tại %ProgramData%\\OGKAgent\\agent_cache.db."""
    base_dir = os.path.expandvars(r"%ProgramData%\OGKAgent")
    try:
        os.makedirs(base_dir, exist_ok=True)
        test_file = os.path.join(base_dir, f".test_write_{os.getpid()}")
        try:
            with open(test_file, "w") as f:
                f.write("1")
            os.remove(test_file)
            return os.path.join(base_dir, "agent_cache.db")
        except Exception:
            pass
    except Exception:
        pass
    fallback = os.path.abspath("./ogk_agent_data")
    os.makedirs(fallback, exist_ok=True)
    return os.path.join(fallback, "agent_cache.db")


class LocalCache:
    """Quản lý lưu trữ SQLite cục bộ cho Agent trong môi trường Online lẫn Offline."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_cache_db_path()
        self.device_id = get_machine_guid()
        self.child_id = 1
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    # 1. Bản sao chính sách (Policy)
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS cached_policy (
                            child_id INTEGER PRIMARY KEY,
                            version INTEGER DEFAULT 1,
                            daily_quota_weekday_min INTEGER DEFAULT 90,
                            daily_quota_weekend_min INTEGER DEFAULT 120,
                            schedule_matrix TEXT DEFAULT '',
                            blocked_apps TEXT DEFAULT '',
                            blocked_domains TEXT DEFAULT '',
                            updated_at TEXT
                        );
                        """
                    )
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS cached_time_adjustment (
                            child_id INTEGER PRIMARY KEY,
                            day TEXT,
                            minutes INTEGER NOT NULL
                        )
                    """)
                    # 2. Hàng đợi sự kiện (Event Queue - 7 trường chuẩn)
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS event_queue (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            ts TEXT NOT NULL,
                            device_id TEXT NOT NULL,
                            child_id INTEGER NOT NULL,
                            type TEXT NOT NULL,
                            subject TEXT NOT NULL,
                            duration_sec INTEGER DEFAULT 0,
                            policy_id INTEGER,
                            retry_count INTEGER DEFAULT 0
                        );
                        """
                    )
                    # 3. Theo dõi thời gian sử dụng trong ngày
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS daily_usage (
                            usage_date TEXT PRIMARY KEY,
                            used_seconds INTEGER DEFAULT 0,
                            updated_at TEXT
                        );
                        """
                    )
                    conn.commit()
            except Exception as exc:
                print(f"[CACHE_ERROR] Lỗi khởi tạo DB: {exc}")

    def save_policy(self, policy: Dict[str, Any]) -> bool:
        """Lưu bản sao chính sách vào cache SQLite."""
        child_id = policy.get("child_id", self.child_id)
        version = policy.get("version", 1)
        weekday_quota = policy.get("daily_quota_weekday_min", 90)
        weekend_quota = policy.get("daily_quota_weekend_min", 120)
        schedule_matrix = policy.get("schedule_matrix", "1" * 336)
        blocked_apps = policy.get("blocked_apps", "")
        blocked_domains = policy.get("blocked_domains", "")
        updated_at = datetime.datetime.utcnow().isoformat()

        with self._lock:
            try:
                with self._get_connection() as conn:
                    conn.execute(
                        """
                        INSERT INTO cached_policy (
                            child_id, version, daily_quota_weekday_min, daily_quota_weekend_min,
                            schedule_matrix, blocked_apps, blocked_domains, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(child_id) DO UPDATE SET
                            version=excluded.version,
                            daily_quota_weekday_min=excluded.daily_quota_weekday_min,
                            daily_quota_weekend_min=excluded.daily_quota_weekend_min,
                            schedule_matrix=excluded.schedule_matrix,
                            blocked_apps=excluded.blocked_apps,
                            blocked_domains=excluded.blocked_domains,
                            updated_at=excluded.updated_at;
                        """,
                        (
                            child_id,
                            version,
                            weekday_quota,
                            weekend_quota,
                            schedule_matrix,
                            blocked_apps,
                            blocked_domains,
                            updated_at,
                        ),
                    )
                    conn.execute(
                        """INSERT INTO cached_time_adjustment (child_id, day, minutes)
                           VALUES (?, ?, ?)
                           ON CONFLICT(child_id) DO UPDATE SET
                           day=excluded.day, minutes=excluded.minutes""",
                        (child_id, policy.get("adjustment_date"), policy.get("adjustment_minutes", 0)),
                    )
                    conn.commit()
                return True
            except Exception as exc:
                print(f"[CACHE_ERROR] Lỗi lưu policy: {exc}")
                return False

    def get_policy(self, child_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Lấy chính sách đã lưu trong cache."""
        c_id = child_id or self.child_id
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""SELECT p.*, a.day AS adjustment_date, a.minutes AS adjustment_minutes
                        FROM cached_policy p LEFT JOIN cached_time_adjustment a USING (child_id)
                        WHERE p.child_id = ?;""", (c_id,))
                    row = cursor.fetchone()
                    if row:
                        return dict(row)
            except Exception as exc:
                print(f"[CACHE_ERROR] Lỗi đọc policy: {exc}")
        return None

    def enqueue_event(
        self,
        event_type: str,
        subject: str,
        duration_sec: int = 0,
        policy_id: Optional[int] = 1,
        child_id: Optional[int] = None,
        ts: Optional[str] = None,
    ) -> bool:
        """Đưa sự kiện vào hàng đợi SQLite theo lược đồ 7 trường chuẩn."""
        now_iso = ts or datetime.datetime.utcnow().isoformat()
        c_id = child_id or self.child_id

        with self._lock:
            try:
                with self._get_connection() as conn:
                    conn.execute(
                        """
                        INSERT INTO event_queue (
                            ts, device_id, child_id, type, subject, duration_sec, policy_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?);
                        """,
                        (now_iso, self.device_id, c_id, event_type, subject, duration_sec, policy_id),
                    )
                    conn.commit()
                return True
            except Exception as exc:
                print(f"[CACHE_ERROR] Lỗi đưa sự kiện vào queue: {exc}")
                return False

    def peek_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Lấy danh sách các sự kiện chưa gửi."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM event_queue ORDER BY id ASC LIMIT ?;", (limit,))
                    return [dict(r) for r in cursor.fetchall()]
            except Exception:
                return []

    def delete_events(self, event_ids: List[int]) -> bool:
        """Xóa các sự kiện đã gửi thành công."""
        if not event_ids:
            return True
        with self._lock:
            try:
                with self._get_connection() as conn:
                    placeholders = ",".join("?" for _ in event_ids)
                    conn.execute(f"DELETE FROM event_queue WHERE id IN ({placeholders});", event_ids)
                    conn.commit()
                return True
            except Exception:
                return False

    def get_pending_event_count(self) -> int:
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM event_queue;")
                    res = cursor.fetchone()
                    return res[0] if res else 0
            except Exception:
                return 0

    def add_daily_usage(self, additional_seconds: int) -> int:
        today = datetime.date.today().isoformat()
        now_iso = datetime.datetime.utcnow().isoformat()
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT INTO daily_usage (usage_date, used_seconds, updated_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(usage_date) DO UPDATE SET
                            used_seconds = used_seconds + excluded.used_seconds,
                            updated_at = excluded.updated_at;
                        """,
                        (today, additional_seconds, now_iso),
                    )
                    conn.commit()
                    cursor.execute("SELECT used_seconds FROM daily_usage WHERE usage_date = ?;", (today,))
                    row = cursor.fetchone()
                    return row[0] if row else 0
            except Exception:
                return 0

    def get_today_usage_seconds(self) -> int:
        today = datetime.date.today().isoformat()
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT used_seconds FROM daily_usage WHERE usage_date = ?;", (today,))
                    row = cursor.fetchone()
                    return row[0] if row else 0
            except Exception:
                return 0


local_cache = LocalCache()


def flush_events_if_online(server_url: str = "http://127.0.0.1:8000") -> int:
    """Hàm tiện ích đẩy sự kiện lên server và xóa cache khi nhận HTTP 200/201."""
    import requests
    events = local_cache.peek_events(50)
    if not events:
        return 0
    batch_payload = [
        {
            "ts": ev["ts"],
            "device_id": ev["device_id"],
            "child_id": ev["child_id"],
            "type": ev["type"],
            "subject": ev["subject"],
            "duration_sec": ev["duration_sec"],
            "policy_id": ev["policy_id"],
        }
        for ev in events
    ]
    ids = [ev["id"] for ev in events]
    try:
        resp = requests.post(f"{server_url}/events/batch", json=batch_payload, timeout=5.0)
        if resp.status_code in (200, 201):
            local_cache.delete_events(ids)
            return len(batch_payload)
    except Exception:
        pass
    return 0


