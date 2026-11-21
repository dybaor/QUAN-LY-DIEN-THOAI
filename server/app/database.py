from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import DB_PATH

DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 15},
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Cột bổ sung cho cơ sở dữ liệu tạo bởi phiên bản cũ: {bảng: {cột: định nghĩa}}
_MIGRATIONS = {
    "parents": {
        "role": "VARCHAR(20) DEFAULT 'parent'",
        "failed_login_count": "INTEGER DEFAULT 0",
        "locked_until": "DATETIME",
    },
    "devices": {
        "policy_key": "VARCHAR(255)",
        "last_seen": "DATETIME",
        "ui_present": "BOOLEAN DEFAULT 1",
    },
    "policies": {
        "child_name": "VARCHAR(255)",
        "lock_pin": "VARCHAR(50)",
        "lock_password_hash": "VARCHAR(255)",
        "pin_failed_count": "INTEGER DEFAULT 0",
        "pin_locked_until": "DATETIME",
        "blocked_categories": "VARCHAR(255) DEFAULT 'social_media,games,inappropriate'",
        "paused_until": "DATETIME",
    },
    "device_events": {
        "idempotency_key": "VARCHAR(64)",
    },
}


def run_migrations():
    with engine.begin() as conn:
        raw = conn.connection.cursor()
        for table, columns in _MIGRATIONS.items():
            existing = {row[1] for row in raw.execute(f"PRAGMA table_info({table})").fetchall()}
            if not existing:
                continue
            for name, ddl in columns.items():
                if name not in existing:
                    raw.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        raw.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_device_events_idempotency "
            "ON device_events(idempotency_key) WHERE idempotency_key IS NOT NULL"
        )
        raw.close()


def close_all_connections():
    engine.dispose()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
