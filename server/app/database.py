import sys
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

if getattr(sys, "frozen", False):
    DB_PATH = Path(sys.executable).resolve().parent / "ogk_system.db"
else:
    DB_PATH = Path(__file__).resolve().parent.parent.parent / "ogk_system.db"

DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False, "timeout": 15}
)

# Kích hoạt pragma an toàn cho SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def ensure_policy_columns():
    """Tự động thêm cột child_name, lock_pin, lock_password_hash vào bảng policies nếu thiếu (Mặc định NULL)."""
    try:
        with engine.begin() as conn:
            cursor = conn.connection.cursor()
            existing_cols = [c[1] for c in cursor.execute("PRAGMA table_info(policies)").fetchall()]
            if existing_cols:
                if "child_name" not in existing_cols:
                    cursor.execute("ALTER TABLE policies ADD COLUMN child_name VARCHAR(100) DEFAULT NULL")
                if "lock_pin" not in existing_cols:
                    cursor.execute("ALTER TABLE policies ADD COLUMN lock_pin VARCHAR(50) DEFAULT NULL")
                if "lock_password_hash" not in existing_cols:
                    cursor.execute("ALTER TABLE policies ADD COLUMN lock_password_hash VARCHAR(255) DEFAULT NULL")
            cursor.close()
    except Exception:
        pass

ensure_policy_columns()

def close_all_connections():
    """Đóng toàn bộ connection pool của engine SQLite."""
    try:
        engine.dispose()
    except Exception:
        pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()