#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
OGK SYSTEM - SCRIPT TỰ ĐỘNG RESET CƠ SỞ DỮ LIỆU SẠCH (CLEAN DATABASE RESET)
================================================================================
Mục đích:
  1. Đóng toàn bộ kết nối SQLite đang mở.
  2. Xóa bỏ hoàn toàn các file dữ liệu SQLite cũ (ogk_system.db, db-shm, db-wal)
     tại thư mục gốc, thư mục server/, và các thư mục liên quan.
  3. Khởi tạo lại cấu trúc bảng mới với giá trị mặc định:
     child_name = NULL, lock_pin = NULL, lock_password_hash = NULL.
  4. Đảm bảo hệ thống ở TRƯỜNG HỢP A (Sạch 100%, sẵn sàng cho Onboarding lần đầu).
================================================================================
"""

import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SERVER_DIR = BASE_DIR / "server"

for p in [str(BASE_DIR), str(SERVER_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from app.database import engine, close_all_connections, Base, SessionLocal
from app.models import Parent, Child, Policy, DeviceEvent, TimeRequest, MonitoringSession, AccessHistoryLog


def clean_and_reset_database():
    print("=" * 65)
    print("  OGK SYSTEM - TIẾN HÀNH RESET CƠ SỞ DỮ LIỆU SẠCH (CLEAN RESET)")
    print("=" * 65)

    # 1. Đóng toàn bộ kết nối SQLite đang mở
    print("[1/4] Đóng tất cả kết nối SQLite pool...")
    close_all_connections()
    time.sleep(0.2)

    # 2. Xóa bỏ hoàn toàn các file database cũ
    print("[2/4] Xóa các file SQLite cũ (*.db, *.db-shm, *.db-wal)...")
    target_dirs = [BASE_DIR, SERVER_DIR, BASE_DIR / "dist_package"]
    deleted_files = []

    for d in target_dirs:
        if not d.exists():
            continue
        for db_file in d.glob("ogk_system.db*"):
            try:
                db_file.unlink()
                deleted_files.append(str(db_file))
                print(f"  [-] Đã xóa: {db_file}")
            except Exception as e:
                print(f"  [!] Không thể xóa {db_file}: {e}")

    # 3. Tạo lại cấu trúc bảng SQLite sạch
    print("[3/4] Khởi tạo cấu trúc bảng SQLite mới...")
    Base.metadata.create_all(bind=engine)

    # 4. Tạo bản ghi ban đầu: child_name = NULL, lock_pin = NULL
    print("[4/4] Nạp bản ghi cơ bản với child_name = NULL, lock_pin = NULL...")
    db = SessionLocal()
    try:
        sample_parent = Parent(
            username="phuhuynh1", 
            hashed_password="hashed_dummy_password"
        )
        db.add(sample_parent)
        db.commit()
        db.refresh(sample_parent)

        sample_child = Child(
            name=None, 
            age=10, 
            parent_id=sample_parent.id
        )
        db.add(sample_child)
        db.commit()
        db.refresh(sample_child)

        initial_policy = Policy(
            child_id=sample_child.id,
            child_name=None,
            lock_pin=None,
            lock_password_hash=None,
            daily_quota_weekday_min=120,
            daily_quota_weekend_min=180,
            schedule_matrix="1" * 168,
            blocked_apps="",
            blocked_domains="",
            version=1
        )
        db.add(initial_policy)
        db.commit()
        db.refresh(initial_policy)

        print("=" * 65)
        print("[THÀNH CÔNG] Cơ sở dữ liệu đã được đưa về trạng thái sạch hoàn toàn:")
        print(f"  - Tên của bé : NULL / None (Chưa thiết lập)")
        print(f"  - Mã PIN      : NULL / None (Chưa thiết lập)")
        print(f"  - Hash PIN    : NULL / None (Chưa thiết lập)")
        print(f"  - Trạng thái  : TRƯỜNG HỢP A (Bật Onboarding Thiết lập Hồ sơ Ban đầu)")
        print("=" * 65)
        return True
    except Exception as e:
        db.rollback()
        print(f"[LỖI] Khởi tạo cơ sở dữ liệu thất bại: {e}")
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = clean_and_reset_database()
    if not success:
        sys.exit(1)
