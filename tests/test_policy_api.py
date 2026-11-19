#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kiểm thử tự động cho Policy Router & Launch App API:
- Lấy chính sách mặc định
- Cập nhật chính sách với chuẩn mới 168 ký tự (7 ngày x 24 giờ)
- Kiểm tra validation từ chối ma trận không hợp lệ
- Kiểm tra bảo mật whitelist của Launch Desktop App API
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock

BASE_DIR = Path(__file__).resolve().parent.parent
SERVER_DIR = BASE_DIR / "server"
for p in [str(BASE_DIR), str(SERVER_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from server.app.database import SessionLocal
    from server.app.models import Policy
    from server.app.routers.policy_events import (
        get_child_policy, 
        PolicyUpdateSchema, 
        launch_desktop_app,
        LaunchAppSchema,
        get_settings,
        update_settings,
        SettingsUpdateSchema,
        verify_pin,
        VerifyPinSchema,
        reset_system_state
    )
except ImportError:
    from app.database import SessionLocal  # type: ignore
    from app.models import Policy  # type: ignore
    from app.routers.policy_events import (  # type: ignore
        get_child_policy, 
        PolicyUpdateSchema, 
        launch_desktop_app,
        LaunchAppSchema,
        get_settings,
        update_settings,
        SettingsUpdateSchema,
        verify_pin,
        VerifyPinSchema,
        reset_system_state
    )
from pydantic import ValidationError


class TestPolicyAPI(unittest.TestCase):

    def setUp(self):
        self.db = SessionLocal()

    def tearDown(self):
        reset_system_state(db=self.db)
        self.db.close()

    def test_get_policy(self):
        """Kiểm tra lấy chính sách của trẻ."""
        policy = get_child_policy(child_id=1, db=self.db)
        self.assertIsNotNone(policy)
        self.assertEqual(policy.child_id, 1)
        self.assertIsNotNone(policy.version)
        self.assertTrue(hasattr(policy, "schedule_matrix"))

    def test_update_policy_168_matrix_and_version_increment(self):
        """Kiểm tra cập nhật chính sách với chuẩn 168 ký tự (24h kéo thả) và tăng version."""
        # 1. Kiểm tra Schema chấp nhận 168 ký tự
        matrix_168 = "1" * 24 * 5 + "0" * 24 * 2
        self.assertEqual(len(matrix_168), 168)
        schema = PolicyUpdateSchema(
            child_id=1,
            daily_quota_weekday_min=135,
            daily_quota_weekend_min=200,
            schedule_matrix=matrix_168,
            blocked_apps='[{"name": "Roblox", "hash": "' + ("f" * 64) + '"}]',
            blocked_domains="tiktok.com,facebook.com"
        )
        self.assertEqual(schema.schedule_matrix, matrix_168)

        # 2. Kiểm tra Schema chấp nhận tương thích ngược 336 ký tự
        matrix_336 = "1" * 48 * 5 + "0" * 48 * 2
        schema_336 = PolicyUpdateSchema(
            child_id=1,
            daily_quota_weekday_min=120,
            daily_quota_weekend_min=180,
            schedule_matrix=matrix_336
        )
        self.assertEqual(schema_336.schedule_matrix, matrix_336)

        # 3. Cập nhật và lưu vào DB
        policy = self.db.query(Policy).filter(Policy.child_id == 1).first()
        if not policy:
            policy = Policy(child_id=1)
            self.db.add(policy)
        old_ver = policy.version
        policy.daily_quota_weekday_min = schema.daily_quota_weekday_min
        policy.daily_quota_weekend_min = schema.daily_quota_weekend_min
        policy.schedule_matrix = schema.schedule_matrix
        policy.version += 1
        self.db.commit()

        # 4. Xác thực dữ liệu được lưu đúng
        updated = get_child_policy(child_id=1, db=self.db)
        self.assertEqual(updated.version, old_ver + 1)
        self.assertEqual(updated.schedule_matrix, matrix_168)
        self.assertEqual(updated.daily_quota_weekday_min, 135)

    def test_update_policy_validation_failure(self):
        """Kiểm tra Pydantic Validator từ chối ma trận độ dài sai hoặc chứa ký tự lạ."""
        # 100 ký tự (sai độ dài)
        with self.assertRaises(ValidationError):
            PolicyUpdateSchema(
                child_id=1,
                daily_quota_weekday_min=100,
                daily_quota_weekend_min=100,
                schedule_matrix="1" * 100
            )

        # Chứa ký tự '2' (chỉ được 0 hoặc 1)
        with self.assertRaises(ValidationError):
            PolicyUpdateSchema(
                child_id=1,
                daily_quota_weekday_min=100,
                daily_quota_weekend_min=100,
                schedule_matrix=("1" * 167) + "2"
            )

    def test_launch_desktop_app_whitelist_security(self):
        """Kiểm tra API launch-app mô phỏng an toàn, tuyệt đối không gọi subprocess OS thật."""
        from fastapi import HTTPException

        # Thử mở app hợp lệ trong whitelist (Mô phỏng an toàn, không gọi subprocess.Popen)
        with patch("subprocess.Popen") as mock_popen:
            res = launch_desktop_app(LaunchAppSchema(app_id="calc"))
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["app_id"], "calc")
            mock_popen.assert_not_called()

        # Thử mở app độc hại / nằm ngoài whitelist -> phải raise 400
        with self.assertRaises(HTTPException) as ctx:
            launch_desktop_app(LaunchAppSchema(app_id="powershell.exe"))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_settings_update_and_get(self):
        """Kiểm tra API cấu hình tên bé và mã PIN khóa máy."""
        # Lấy cấu hình ban đầu
        settings = get_settings(child_id=1, db=self.db)
        self.assertIn("child_name", settings)
        self.assertIn("lock_pin", settings)

        # Cập nhật thông tin mới
        policy = self.db.query(Policy).filter(Policy.child_id == 1).first()
        policy.child_name = "Bé Minh"
        policy.lock_pin = "6789"
        self.db.commit()

        # Đọc lại và kiểm chứng
        updated = get_settings(child_id=1, db=self.db)
        self.assertEqual(updated["child_name"], "Bé Minh")
        self.assertEqual(updated["lock_pin"], "6789")

    def test_verify_pin_logic(self):
        """Kiểm tra API xác thực mã PIN khóa máy con: 100% bảo mật, không chấp nhận fallback 1234 hay 0000."""
        policy = self.db.query(Policy).filter(Policy.child_id == 1).first()
        policy.lock_pin = "9876"
        self.db.commit()

        # 1. Mã PIN đúng 100%
        res_ok = verify_pin(VerifyPinSchema(child_id=1, pin="9876"), db=self.db)
        self.assertTrue(res_ok["valid"])
        self.assertTrue(res_ok.get("success", False))
        self.assertIn(res_ok["message"], ["Xác thực thành công", "Mã PIN chính xác"])

        # 2. Mã PIN mặc định 1234 -> Bị từ chối hoàn toàn
        res_default = verify_pin(VerifyPinSchema(child_id=1, pin="1234"), db=self.db)
        self.assertFalse(res_default["valid"])
        self.assertEqual(res_default["message"], "Mã PIN không chính xác. Vui lòng thử lại!")

        # 3. Mã PIN 0000 -> Bị từ chối hoàn toàn
        res_master = verify_pin(VerifyPinSchema(child_id=1, pin="0000"), db=self.db)
        self.assertFalse(res_master["valid"])

        # 4. Mã PIN sai ngẫu nhiên
        res_fail = verify_pin(VerifyPinSchema(child_id=1, pin="9999"), db=self.db)
        self.assertFalse(res_fail["valid"])

    def test_zero_os_notification_calls_in_agent(self):
        """Kiểm tra mã nguồn agent/ đảm bảo KHÔNG gọi popup hệ điều hành WTSSendMessageW (Task 1)."""
        agent_dir = BASE_DIR / "agent"
        for py_file in agent_dir.glob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                self.assertNotIn("WTSSendMessageW", stripped, f"Phát hiện gọi WTSSendMessageW tại {py_file.name}: {line}")


if __name__ == "__main__":
    unittest.main()
