#!/usr/bin/env python3
"""Đưa cơ sở dữ liệu OGK về trạng thái sạch (chưa có tài khoản phụ huynh) để demo luồng tạo tài khoản.

Chạy qua launcher: `Start_App.bat --reset` (Windows) hoặc `./Start_App.command --reset` (macOS).
Máy chủ phải đang tắt. Khóa bí mật (ogk_secrets.json) được giữ nguyên.
"""

import sys

for _stream in (sys.stdout, sys.stderr):  # In tiếng Việt được cả khi ghi log ra file / CI
    if _stream and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent / "server"
sys.path.insert(0, str(SERVER_DIR))

from app.config import DB_PATH  # noqa: E402


def clean_and_reset_database() -> bool:
    print(f"[OGK] Xóa cơ sở dữ liệu: {DB_PATH}")
    for suffix in ("", "-wal", "-shm"):
        target = Path(str(DB_PATH) + suffix)
        try:
            target.unlink(missing_ok=True)
        except PermissionError:
            print(f"[LỖI] {target.name} đang được sử dụng. Hãy tắt máy chủ OGK rồi chạy lại.")
            return False
    from app.database import Base, engine, run_migrations
    import app.models  # noqa: F401  (đăng ký bảng)
    Base.metadata.create_all(bind=engine)
    run_migrations()
    engine.dispose()
    print("[OGK] Đã tạo cơ sở dữ liệu trống. Mở Dashboard để tạo tài khoản phụ huynh.")
    return True


if __name__ == "__main__":
    sys.exit(0 if clean_and_reset_database() else 1)
