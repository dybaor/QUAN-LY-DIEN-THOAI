#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
OGK SYSTEM - VERIFICATION SCRIPT: VERIFY AUTH & PIN MATCHING FLOW
================================================================================
Kịch bản kiểm chứng tự động:
1. Xóa DB cũ, tạo DB mới sạch (Case A: child_name = NULL, lock_pin = NULL).
2. Kiểm tra trạng thái ban đầu qua get_auth_settings -> is_initialized = False.
3. Gọi API tạo profile lần đầu (Tên: "Bé An", PIN: "1234") -> success = True.
4. Kiểm tra lại get_auth_settings -> is_initialized = True, child_name = "Bé An".
5. Gọi API verify-pin với PIN đúng "1234" -> mong đợi success = True, child_name = "Bé An".
6. Gọi API verify-pin với PIN sai "9999" -> mong đợi success = False.
7. Đưa DB về trạng thái sạch (Case A) sau khi kiểm thử.
================================================================================
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SERVER_DIR = BASE_DIR / "server"

for p in [str(BASE_DIR), str(SERVER_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from reset_database import clean_and_reset_database
from app.database import SessionLocal
from app.routers.policy_events import (
    get_auth_settings,
    update_settings,
    SettingsUpdateSchema,
    verify_pin,
    VerifyPinSchema
)


def run_verification():
    print("=" * 65)
    print("  BẮT ĐẦU KIỂM CHỨNG TỰ ĐỘNG QUY TRÌNH AUTH & SO KHỚP PIN")
    print("=" * 65)

    # 1. Xóa DB cũ, tạo DB mới sạch
    print("\n[Bước 1] Reset database về trạng thái sạch (Case A)...")
    assert clean_and_reset_database() is True, "Reset database thất bại!"

    db = SessionLocal()
    try:
        # 2. Kiểm tra trạng thái ban đầu
        print("\n[Bước 2] Kiểm tra trạng thái xác thực ban đầu (Case A)...")
        data_status = get_auth_settings(child_id=1, db=db)
        print("  -> Dữ liệu trạng thái ban đầu:", data_status)
        assert data_status.get("is_initialized") is False, "Lỗi: Hệ thống mới mà is_initialized lại là True!"
        assert data_status.get("has_pin") is False, "Lỗi: Hệ thống mới mà has_pin lại là True!"
        assert not data_status.get("child_name"), "Lỗi: child_name không rỗng/null!"
        print("  [OK] Xác nhận hệ thống ở trạng thái Case A (chưa khởi tạo profile).")

        # 3. Gọi API tạo profile lần đầu (Tên: "Bé An", PIN: "1234")
        print("\n[Bước 3] Gọi API tạo profile lần đầu (Tên: 'Bé An', PIN: '1234')...")
        init_req = SettingsUpdateSchema(child_id=1, child_name="Bé An", lock_pin="1234")
        data_init = update_settings(init_req, background_tasks=None, db=db)
        print("  -> Kết quả khởi tạo:", data_init)
        assert data_init.get("success") is True or data_init.get("status") == "success", "Init thất bại!"
        assert data_init.get("child_name") == "Bé An", "Tên bé không khớp!"
        assert data_init.get("lock_pin") == "1234", "Mã PIN không khớp!"
        print("  [OK] Đã thiết lập thành công hồ sơ ban đầu.")

        # 4. Kiểm tra lại trạng thái sau khi khởi tạo
        print("\n[Bước 4] Kiểm tra lại trạng thái sau khi thiết lập (Case B)...")
        data_status2 = get_auth_settings(child_id=1, db=db)
        print("  -> Dữ liệu trạng thái mới:", data_status2)
        assert data_status2.get("is_initialized") is True, "Lỗi: Đã thiết lập nhưng is_initialized vẫn là False!"
        assert data_status2.get("has_pin") is True, "Lỗi: Đã thiết lập nhưng has_pin vẫn là False!"
        assert data_status2.get("child_name") == "Bé An", "Lỗi: child_name không phải 'Bé An'!"
        print("  [OK] Xác nhận hệ thống đã chuyển sang Case B (đã có PIN & Tên bé).")

        # 5. Gọi API verify với PIN đúng "1234"
        print("\n[Bước 5] Gọi API verify-pin với PIN đúng '1234'...")
        res_ok = verify_pin(VerifyPinSchema(child_id=1, pin="1234"), db=db)
        print("  -> Kết quả xác thực PIN đúng:", res_ok)
        assert res_ok.get("success") is True, f"Lỗi: PIN đúng nhưng success lại là False: {res_ok}"
        assert res_ok.get("valid") is True, "Lỗi: valid không phải True"
        assert res_ok.get("child_name") == "Bé An", "Lỗi: child_name không trả về 'Bé An'"

        # Thử nghiệm gửi request dạng chỉ có { pin: "1234" }
        res_ok_no_id = verify_pin(VerifyPinSchema(pin="1234"), db=db)
        assert res_ok_no_id.get("success") is True, "Lỗi: Gọi không có child_id thất bại!"
        print("  [OK] Xác thực PIN '1234' thành công 100% (success: True, child_name: 'Bé An').")

        # 6. Gọi API verify với PIN sai "9999"
        print("\n[Bước 6] Gọi API verify-pin với PIN sai '9999'...")
        res_fail = verify_pin(VerifyPinSchema(child_id=1, pin="9999"), db=db)
        print("  -> Kết quả xác thực PIN sai:", res_fail)
        assert res_fail.get("success") is False, f"Lỗi: PIN sai nhưng success lại là True: {res_fail}"
        assert res_fail.get("valid") is False, "Lỗi: valid không phải False"
        print("  [OK] Xác thực PIN '9999' bị từ chối chính xác (success: False).")

        # Kiểm tra thử PIN mặc định "0000" cũng phải bị từ chối
        res_fail_0000 = verify_pin(VerifyPinSchema(child_id=1, pin="0000"), db=db)
        assert res_fail_0000.get("success") is False
        print("  [OK] PIN mặc định '0000' bị từ chối chính xác.")

    finally:
        db.close()

    # 7. Đưa database về trạng thái sạch Case A
    print("\n[Bước 7] Hoàn tất, đưa database về trạng thái sạch (Case A)...")
    assert clean_and_reset_database() is True
    print("  [OK] Cơ sở dữ liệu đã trở lại trạng thái sạch hoàn toàn (Case A).")

    print("\n" + "=" * 65)
    print("  TẤT CẢ 7 BƯỚC KIỂM CHỨNG TỰ ĐỘNG ĐỀU THÀNH CÔNG RỰC RỠ!")
    print("=" * 65)
    return True


if __name__ == "__main__":
    try:
        success = run_verification()
        if not success:
            sys.exit(1)
    except AssertionError as e:
        print(f"\n[ASSERTION ERROR]: {e}")
        sys.exit(1)
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
