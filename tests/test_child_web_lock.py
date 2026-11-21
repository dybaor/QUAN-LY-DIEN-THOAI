#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bộ kiểm thử tự động xác thực hệ thống Cửa sổ Trẻ em (Child Web Portal):
1. Giao diện Web Portal của trẻ (GET /child) phục vụ mã HTTP 200 kèm cấu trúc DOM chuẩn.
2. Khắc phục triệt để lỗi Fullscreen: TUYỆT ĐỐI KHÔNG chứa requestFullscreen hay can thiệp OS fullscreen.
3. Tài nguyên Static (child.css, child.js) hoạt động hoàn hảo.
4. Quản lý WebSocket chuyên biệt (/ws/child/{guid}) kết nối và dọn dẹp an toàn.
5. Luồng xin thêm giờ (Time Extension Request) hoạt động chính xác.
"""

import os
import sys
import unittest
from pathlib import Path
from starlette.requests import Request
from unittest.mock import MagicMock

# Đảm bảo đường dẫn import
BASE_DIR = Path(__file__).resolve().parent.parent
SERVER_DIR = BASE_DIR / "server"
for p in [str(BASE_DIR), str(SERVER_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from app.main import serve_child_portal
from app.websocket_manager import manager


class TestChildWebLock(unittest.TestCase):

    def test_get_child_portal_html_and_dom_elements(self):
        """Kiểm tra route GET /child trả về HTTP 200 và đầy đủ cấu trúc DOM chuẩn."""
        req = Request({"type": "http", "method": "GET", "path": "/child", "headers": []})
        resp = serve_child_portal(req)
        self.assertEqual(resp.status_code, 200, "Route /child phải trả về HTTP 200")
        
        html = resp.body.decode("utf-8")
        # Kiểm tra các ID phần tử giao diện bắt buộc
        self.assertIn('id="lockOverlay"', html, "Phải có lớp phủ In-Page Lock #lockOverlay")
        self.assertIn('id="searchAppInput"', html, "Phải có ô tìm kiếm tương tác #searchAppInput")
        self.assertIn('id="appGrid"', html, "Phải có lưới ứng dụng #appGrid")
        self.assertIn('id="remainingMinutes"', html, "Phải có hiển thị số phút còn lại #remainingMinutes")
        self.assertIn('id="timeProgressBar"', html, "Phải có thanh tiến trình #timeProgressBar")
        self.assertIn('id="inAppBrowserModal"', html, "Phải có modal Safe Browser nội bộ #inAppBrowserModal")
        self.assertIn('id="internalBrowserFrame"', html, "Phải có iframe an toàn #internalBrowserFrame")
        self.assertIn('id="parentPinInput"', html, "Phải có ô nhập PIN phụ huynh #parentPinInput")
        self.assertIn('/static/css/child.css', html, "Phải liên kết file child.css")
        self.assertIn('/static/js/child.js', html, "Phải liên kết file child.js")

    def test_zero_fullscreen_calls_in_child_codebase(self):
        """Kiểm tra TUYỆT ĐỐI KHÔNG có lệnh requestFullscreen hay window.fullscreen trong mã nguồn Child Portal."""
        files_to_check = [
            SERVER_DIR / "templates" / "child_portal.html",
            SERVER_DIR / "static" / "js" / "child.js",
            SERVER_DIR / "static" / "css" / "child.css"
        ]

        forbidden_patterns = [
            "requestFullscreen",
            "requestFullScreen",
            "webkitRequestFullscreen",
            "msRequestFullscreen",
            "window.fullscreen",
            "SW_MAXIMIZE"
        ]

        for file_path in files_to_check:
            self.assertTrue(file_path.exists(), f"File {file_path.name} phải tồn tại")
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            for pattern in forbidden_patterns:
                self.assertNotIn(
                    pattern, 
                    content, 
                    f"Phát hiện vi phạm: {file_path.name} chứa lệnh cấm '{pattern}' làm kích hoạt Fullscreen OS!"
                )

    def test_static_css_and_js_files_exist_and_styled(self):
        """Kiểm tra file static CSS và JS tồn tại và chứa đầy đủ logic màn hình khóa."""
        css_file = SERVER_DIR / "static" / "css" / "child.css"
        self.assertTrue(css_file.exists(), "File child.css phải tồn tại")
        css_text = css_file.read_text(encoding="utf-8")
        self.assertIn("#lockOverlay", css_text, "child.css phải chứa quy tắc styling cho #lockOverlay")
        self.assertIn("backdrop-filter: blur", css_text, "child.css phải có hiệu ứng mờ kính Glassmorphism")

        js_file = SERVER_DIR / "static" / "js" / "child.js"
        self.assertTrue(js_file.exists(), "File child.js phải tồn tại")
        js_text = js_file.read_text(encoding="utf-8")
        self.assertIn("showLockOverlay", js_text, "child.js phải chứa hàm showLockOverlay")
        self.assertIn("hideLockOverlay", js_text, "child.js phải chứa hàm hideLockOverlay")
        self.assertIn("openInAppBrowser", js_text, "child.js phải chứa hàm In-App Safe Browser")

    def test_child_websocket_manager_registration_and_cleanup(self):
        """Kiểm tra logic quản lý kết nối của endpoint WebSocket chuyên biệt /ws/child/{guid}."""
        guid = "unit_test_child_portal_001"
        device_key = f"child_{guid}"
        mock_ws = MagicMock()

        # Giả lập kết nối
        manager.active_connections[device_key].add(mock_ws)
        self.assertIn(device_key, manager.active_connections, "WebSocket phải được lưu trong ConnectionManager")
        self.assertIn(mock_ws, manager.active_connections[device_key])

        # Giả lập ngắt kết nối
        manager.disconnect(device_key, mock_ws)
        self.assertNotIn(device_key, manager.active_connections, "Phải dọn dẹp kết nối khi client ngắt kết nối")



def test_time_request_creation_from_portal(parent, portal):
    """Trẻ xin thêm giờ từ cổng học tập; phụ huynh thấy yêu cầu đang chờ."""
    res = portal.client.post("/api/child/time-requests", json={
        "requested_minutes": 15, "reason": "Bé An xin thêm 15 phút làm bài tập kiểm tra toán"})
    assert res.status_code == 200 and res.json()["request_id"]
    pending = parent.client.get(f"/requests/{parent.child_id}").json()
    assert any(r["id"] == res.json()["request_id"] and r["status"] == "pending" for r in pending)


if __name__ == "__main__":
    unittest.main()
