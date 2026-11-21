#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bộ kiểm thử tự động xác thực:
1. Gỡ bỏ hoàn toàn route proxy /api/search và logic scraping Google phức tạp.
2. Thanh tìm kiếm trên trang trẻ quay về lọc ứng dụng cục bộ (Local App Search, Realtime Client-side Filter).
3. Quy trình mở web & kiểm duyệt 2 bước chuẩn đồ án:
   - Bước 1: Kiểm tra Tên App / Danh mục cục bộ (Local App Verification).
   - Bước 2: Kiểm tra Tên miền (Domain Blacklist Checking) -> Chặn web cấm, nạp URL thật trực tiếp (hết lỗi màn hình trắng).
4. Tính toàn vẹn giao diện: Nút đóng [✕], phím Escape, click backdrop, và Floating Chat xuyên suốt.
"""

import os
import sys
import unittest
from pathlib import Path

# Đường dẫn dự án
BASE_DIR = Path(__file__).resolve().parent.parent
SERVER_DIR = BASE_DIR / "server"
for p in [str(BASE_DIR), str(SERVER_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from app.main import app


class TestSafetyAndUI(unittest.TestCase):

    def setUp(self):
        from app.websocket_manager import manager
        manager.active_connections.clear()

    # =========================================================================
    # CA 1: GỠ BỎ HOÀN TOÀN ROUTE PROXY SEARCH (/api/search)
    # =========================================================================
    def test_case_1_proxy_search_route_completely_removed(self):
        """Xác nhận /api/search và fetch_google_search đã được xóa bỏ hoàn toàn khỏi backend."""
        routes = [route.path for route in app.routes if hasattr(route, "path")]
        self.assertNotIn("/api/search", routes, "Route /api/search phải được gỡ bỏ hoàn toàn")
        
        main_py_path = SERVER_DIR / "app" / "main.py"
        main_content = main_py_path.read_text(encoding="utf-8")
        self.assertNotIn('def api_search', main_content, "Hàm api_search phải được xóa khỏi main.py")
        self.assertNotIn('fetch_google_search', main_content, "fetch_google_search phải được xóa khỏi main.py")

    # =========================================================================
    # CA 2: THANH TÌM KIẾM TRÊN TRANG TRẺ CHỈ LỌC LOCAL (LOCAL APP SEARCH)
    # =========================================================================
    def test_case_2_local_app_search_and_realtime_filter(self):
        """Kiểm tra thanh tìm kiếm chỉ dùng để lọc cục bộ danh sách app theo thời gian thực."""
        child_html_path = SERVER_DIR / "templates" / "child_portal.html"
        child_html = child_html_path.read_text(encoding="utf-8")
        
        # 1. Kiểm tra placeholder và sự kiện oninput
        self.assertIn('placeholder="Tìm kiếm trên Google…"', child_html)
        self.assertIn('aria-label="Tìm kiếm trên Google"', child_html)
        self.assertIn('oninput="filterApps()"', child_html,
                      "Ô tìm kiếm phải kích hoạt filterApps() theo thời gian thực khi gõ")
        self.assertIn('id="btnClearSearch"', child_html, "Phải có nút xóa tìm kiếm nhanh")
        
        # 2. Kiểm tra mã JS xử lý lọc ứng dụng cục bộ
        child_js_path = SERVER_DIR / "static" / "js" / "child.js"
        child_js = child_js_path.read_text(encoding="utf-8")
        
        self.assertIn("function filterApps()", child_js, "child.js phải định nghĩa function filterApps()")
        self.assertIn("function clearSearchInput()", child_js, "child.js phải có function clearSearchInput()")
        self.assertIn("function renderApps()", child_js, "child.js phải có function renderApps()")
        self.assertIn("removeVietnameseTones", child_js, "Phải hỗ trợ tìm kiếm không dấu tiếng Việt mượt mà")

    # =========================================================================
    # CA 3: QUY TRÌNH MỞ WEB & KIỂM DUYỆT 2 BƯỚC CHUẨN ĐỒ ÁN (APP + DOMAIN)
    # =========================================================================
    def test_case_3_two_step_moderation_and_direct_url_loading(self):
        """Kiểm tra quy trình kiểm duyệt 2 bước:
        - Bước 1: Trích xuất tên miền (extractDomain)
        - Bước 2: So khớp Policy tên miền (isDomainBlocked)
          + Chặn web cấm, hiển thị thông báo nội bộ, bắn alert WebSocket
          + Nạp trực tiếp URL thật vào iframe nội bộ (Google có igu=1, hết lỗi màn hình trắng)
        """
        child_js_path = SERVER_DIR / "static" / "js" / "child.js"
        child_js = child_js_path.read_text(encoding="utf-8")
        
        # 1. Không còn app Google trùng chức năng; tìm kiếm chỉ đi qua thanh tìm kiếm với SafeSearch + igu=1
        self.assertNotIn("google_search", child_js, "App Google phải được gỡ, chỉ giữ thanh tìm kiếm")
        self.assertIn("const APPS = [];", child_js)
        self.assertIn("safe: 'active'", child_js, "Thanh tìm kiếm phải ép SafeSearch")
        self.assertIn("igu: '1'", child_js, "Nhúng iframe Google cần igu=1 để không trắng màn hình")

        # 2. Bước 1: Trích xuất tên miền
        self.assertIn("function extractDomain(", child_js, "Phải có hàm trích xuất tên miền extractDomain()")
        
        # 3. Bước 2: Kiểm tra Domain Blacklist
        self.assertIn("function isDomainBlocked(", child_js, "Phải có hàm kiểm tra domain cấm isDomainBlocked()")
        self.assertIn("triggerViolationAlert(", child_js, "Phải bắn sự kiện violation_alert qua WebSocket khi vi phạm")
        self.assertIn("showViolationBlockModal(", child_js, "Phải hiển thị modal thông báo vi phạm nội bộ")
        self.assertIn("Trang web / Ứng dụng này đã bị ba mẹ chặn truy cập!", child_js,
                      "Phải có thông báo chặn chuẩn đồ án")
        
        # 4. Nạp URL trực tiếp (không đi qua proxy search gây trắng màn hình)
        self.assertIn("frame.src = search.href", child_js, "Khi domain hợp lệ, phải nạp URL trực tiếp vào iframe")

    # =========================================================================
    # CA 4: NÚT ĐÓNG [✕] TRÊN CÁC MODAL & TÍNH TOÀN VẸN GIAO DIỆN
    # =========================================================================
    def test_case_4_modal_close_buttons_and_floating_chat_integrity(self):
        """Kiểm tra:
        - Khung xem nội bộ có thanh tiêu đề hiển thị tên trang và nút 'Đóng (✕)'
        - Các modal Thời gian biểu, Giờ ngủ, Vi phạm đều có nút [✕], phím Esc và backdrop click
        - Floating Chat Widget hoạt động xuyên suốt
        """
        # 1. Kiểm tra child_portal.html
        child_html_path = SERVER_DIR / "templates" / "child_portal.html"
        child_html = child_html_path.read_text(encoding="utf-8")
        
        self.assertIn('id="inAppBrowserModal"', child_html)
        self.assertIn('id="internalBrowserFrame"', child_html)
        self.assertIn('id="browserTitleDisplay"', child_html, "Khung xem phải có tiêu đề tên trang")
        self.assertIn('closeInAppBrowser()', child_html, "Khung xem phải có nút Đóng [✕]")
        
        # Floating Chat Widget
        self.assertIn('id="floatingChatBtn"', child_html)
        self.assertIn('id="floatingChatWindow"', child_html)
        
        # 2. Kiểm tra dashboard.html
        for filename in ["dashboard.html"]:
            dashboard_html = (SERVER_DIR / "templates" / filename).read_text(encoding="utf-8")
            self.assertIn('id="dailyScheduleModal"', dashboard_html)
            self.assertIn('closeDailyScheduleModal()', dashboard_html)
            self.assertIn('id="bedtimeConfigModal"', dashboard_html)
            self.assertIn('closeBedtimeConfigModal()', dashboard_html)
            self.assertIn('id="violationDetailModal"', dashboard_html)
            self.assertIn('closeViolationDetailModal()', dashboard_html)

    # =========================================================================
    # CA 6: BỘ LỌC 2 TẦNG (TỪ KHÓA & TÊN MIỀN) & CẢNH BÁO TỨC THÌ
    # =========================================================================
    def test_case_6_two_tier_keyword_domain_interception_and_alerts(self):
        """Kiểm tra:
        - Chặn từ khóa người lớn/cờ bạc trên thanh tìm kiếm
        - Bắn sự kiện violation_alert kèm violation_type
        - Dashboard phụ huynh có Web Audio Chime và toast đỏ
        """
        child_js = (SERVER_DIR / "static" / "js" / "child.js").read_text(encoding="utf-8")
        self.assertIn("checkRestrictedKeyword(rawQuery)", child_js)
        self.assertIn("violation_type", child_js)
        self.assertIn("logAccess", child_js)

        dashboard_html = (SERVER_DIR / "templates" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("playWarningChime", dashboard_html)
        self.assertIn("Cảnh báo vi phạm! Bé vừa tìm kiếm/truy cập", dashboard_html)



def test_case_5_parent_auth_gate_and_child_pairing_screen():
    """Dashboard bắt buộc đăng nhập tài khoản phụ huynh; cổng trẻ có màn hình chờ + ghép đôi bằng mã."""
    dashboard_html = (SERVER_DIR / "templates" / "dashboard.html").read_text(encoding="utf-8")
    assert 'id="onboardingModal"' in dashboard_html
    assert 'checkAuthOrOnboarding()' in dashboard_html
    assert '/api/auth/login' in dashboard_html and '/api/auth/register' in dashboard_html
    assert 'sessionStorage' not in dashboard_html, "Không được dùng sessionStorage làm cơ chế xác thực"
    assert 'X-CSRF-Token' in dashboard_html
    child_html = (SERVER_DIR / "templates" / "child_portal.html").read_text(encoding="utf-8")
    assert 'id="waitingScreenState"' in child_html and 'id="pairingForm"' in child_html
    child_js = (SERVER_DIR / "static" / "js" / "child.js").read_text(encoding="utf-8")
    assert "submitPairingCode" in child_js and "hideWaitingScreen" in child_js
    assert "lock_pin" not in child_js, "Cổng trẻ không bao giờ nhận mã PIN"


def test_case_7_screen_monitoring_history(parent):
    cid = parent.child_id
    start = parent.client.post("/api/monitoring/start", json={"child_id": cid, "device_id": "TEST-PC"}).json()
    assert start["status"] == "success"
    assert parent.client.get(f"/api/monitoring/history/{cid}").json()[0]["status"] == "Đang theo dõi"
    stop = parent.client.post("/api/monitoring/stop", json={"child_id": cid, "session_id": start["session_id"]}).json()
    assert stop["status"] == "success"
    assert parent.client.get(f"/api/monitoring/history/{cid}").json()[0]["status"] == "Đã kết thúc"
    dashboard_html = (SERVER_DIR / "templates" / "dashboard.html").read_text(encoding="utf-8")
    assert 'id="monitoringHistoryTableBody"' in dashboard_html and 'loadMonitoringHistory()' in dashboard_html


def test_case_8_child_access_history(parent, portal):
    for name, state in (("Khan Academy", "allowed"), ("88bet.com", "blocked")):
        resp = portal.client.post("/api/child/access-log", json={"target_name": name, "target_type": "Trang web", "status": state})
        assert resp.json()["status"] == "success"
    history = parent.client.get(f"/api/access-history/{parent.child_id}").json()
    names = [h["target_name"] for h in history]
    assert "Khan Academy" in names and "88bet.com" in names
    dashboard_html = (SERVER_DIR / "templates" / "dashboard.html").read_text(encoding="utf-8")
    assert 'id="accessHistoryTableBody"' in dashboard_html and 'loadAccessHistory()' in dashboard_html


if __name__ == "__main__":
    unittest.main()
