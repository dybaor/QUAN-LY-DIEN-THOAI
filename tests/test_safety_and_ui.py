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

from app.database import SessionLocal
from app.models import Policy
from app.routers.policy_events import verify_pin, VerifyPinSchema
from app.main import app


class TestSafetyAndUI(unittest.TestCase):

    def setUp(self):
        from app.websocket_manager import manager
        manager.active_connections.clear()
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

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
        self.assertIn('placeholder="Tìm ứng dụng hoặc trang web…"', child_html)
        self.assertIn('aria-label="Tìm ứng dụng hoặc trang web"', child_html)
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
        
        # 1. App Google Tìm Kiếm cài sẵn trong danh mục với tham số igu=1
        self.assertIn("google_search", child_js, "Kho APPS phải có biểu tượng Google Tìm Kiếm")
        self.assertIn("https://www.google.com/webhp?igu=1", child_js,
                      "Google Tìm Kiếm phải dùng link trực tiếp có igu=1 để nhúng iframe không bị trắng màn hình")
        
        # 2. Bước 1: Trích xuất tên miền
        self.assertIn("function extractDomain(", child_js, "Phải có hàm trích xuất tên miền extractDomain()")
        
        # 3. Bước 2: Kiểm tra Domain Blacklist
        self.assertIn("function isDomainBlocked(", child_js, "Phải có hàm kiểm tra domain cấm isDomainBlocked()")
        self.assertIn("triggerViolationAlert(", child_js, "Phải bắn sự kiện violation_alert qua WebSocket khi vi phạm")
        self.assertIn("showViolationBlockModal(", child_js, "Phải hiển thị modal thông báo vi phạm nội bộ")
        self.assertIn("Trang web / Ứng dụng này đã bị ba mẹ chặn truy cập!", child_js,
                      "Phải có thông báo chặn chuẩn đồ án")
        
        # 4. Nạp URL trực tiếp (không đi qua proxy search gây trắng màn hình)
        self.assertIn("frame.src = url", child_js, "Khi domain hợp lệ, phải nạp URL trực tiếp vào iframe")

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
        
        # 2. Kiểm tra dashboard.html và index.html
        for filename in ["dashboard.html", "index.html"]:
            dashboard_html = (SERVER_DIR / "templates" / filename).read_text(encoding="utf-8")
            self.assertIn('id="dailyScheduleModal"', dashboard_html)
            self.assertIn('closeDailyScheduleModal()', dashboard_html)
            self.assertIn('id="bedtimeConfigModal"', dashboard_html)
            self.assertIn('closeBedtimeConfigModal()', dashboard_html)
            self.assertIn('id="violationDetailModal"', dashboard_html)
            self.assertIn('closeViolationDetailModal()', dashboard_html)

    # =========================================================================
    # CA 5: XÁC THỰC PHỤ HUYNH & MÀN HÌNH CHỜ TRANG CON (AUTH & SPLASH)
    # =========================================================================
    def test_case_5_parent_auth_gate_and_child_splash_transition(self):
        """Kiểm tra:
        - Màn hình Auth/Onboarding bảo vệ Dashboard phụ huynh, không cho tắt modal nếu chưa xác thực
        - Xác thực PIN trả về hợp lệ và kích hoạt WebSocket init_completed
        - Cửa sổ trẻ em có waitingScreenState và lắng nghe init_completed để mở giao diện
        """
        # 1. API Verify PIN
        policy = self.db.query(Policy).filter(Policy.child_id == 1).first()
        policy.lock_pin = "8888"
        self.db.commit()

        res = verify_pin(VerifyPinSchema(child_id=1, pin="8888"), db=self.db)
        self.assertTrue(res["valid"])
        self.assertTrue(res["verified"])
        self.assertEqual(res["status"], "success")

        # 2. Kiểm tra template phụ huynh
        dashboard_html = (SERVER_DIR / "templates" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn('id="onboardingModal"', dashboard_html)
        self.assertIn('ogk_parent_auth', dashboard_html)
        self.assertIn('checkAuthOrOnboarding()', dashboard_html)

        # 3. Kiểm tra template trẻ em
        child_html = (SERVER_DIR / "templates" / "child_portal.html").read_text(encoding="utf-8")
        self.assertIn('id="waitingScreenState"', child_html)

        child_js = (SERVER_DIR / "static" / "js" / "child.js").read_text(encoding="utf-8")
        self.assertIn("init_completed", child_js)
        self.assertIn("hideWaitingScreen", child_js)

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

    # =========================================================================
    # CA 7: LỊCH SỬ QUAN SÁT MÀN HÌNH (SCREEN MONITORING AUDIT LOG)
    # =========================================================================
    def test_case_7_screen_monitoring_audit_log(self):
        """Kiểm tra:
        - API Start/Stop monitoring session
        - API Get monitoring history
        - Bảng Lịch sử quan sát màn hình trên dashboard
        """
        from app.routers.policy_events import start_monitoring_session, stop_monitoring_session, get_monitoring_history, MonitoringStartSchema, MonitoringStopSchema

        # 1. Bắt đầu phiên
        start_res = start_monitoring_session(MonitoringStartSchema(child_id=1, device_id="TEST-PC"), db=self.db)
        self.assertEqual(start_res["status"], "success")
        session_id = start_res["session_id"]

        # 2. Lấy lịch sử thấy đang theo dõi
        hist = get_monitoring_history(child_id=1, db=self.db)
        self.assertTrue(len(hist) > 0)
        self.assertEqual(hist[0]["status"], "Đang theo dõi")

        # 3. Kết thúc phiên
        stop_res = stop_monitoring_session(MonitoringStopSchema(session_id=session_id, child_id=1), db=self.db)
        self.assertEqual(stop_res["status"], "success")

        hist_after = get_monitoring_history(child_id=1, db=self.db)
        self.assertEqual(hist_after[0]["status"], "Đã kết thúc")

        # 4. Kiểm tra UI Dashboard
        dashboard_html = (SERVER_DIR / "templates" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn('id="monitoringHistoryTableBody"', dashboard_html)
        self.assertIn('loadMonitoringHistory()', dashboard_html)

    # =========================================================================
    # CA 8: NHẬT KÝ TRUY CẬP THIẾT BỊ (CHILD ACCESS HISTORY)
    # =========================================================================
    def test_case_8_child_access_history(self):
        """Kiểm tra:
        - API ghi nhận access log (allowed và blocked)
        - API lấy danh sách access history
        - Bảng Nhật ký truy cập thiết bị trên dashboard
        """
        from app.routers.policy_events import create_access_log, get_access_history, AccessLogCreateSchema

        # Ghi log hợp lệ
        log1 = create_access_log(AccessLogCreateSchema(
            child_id=1, device_id="TEST-PC", target_name="Khan Academy", target_type="Trang web", status="allowed"
        ), db=self.db)
        self.assertEqual(log1["status"], "success")

        # Ghi log bị chặn
        log2 = create_access_log(AccessLogCreateSchema(
            child_id=1, device_id="TEST-PC", target_name="88bet.com", target_type="Trang web", status="blocked"
        ), db=self.db)
        self.assertEqual(log2["status"], "success")

        # Lấy danh sách lịch sử
        history = get_access_history(child_id=1, db=self.db)
        self.assertTrue(len(history) >= 2)
        target_names = [h["target_name"] for h in history]
        self.assertIn("Khan Academy", target_names)
        self.assertIn("88bet.com", target_names)

        # Kiểm tra UI Dashboard
        dashboard_html = (SERVER_DIR / "templates" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn('id="accessHistoryTableBody"', dashboard_html)
        self.assertIn('loadAccessHistory()', dashboard_html)

    # =========================================================================
    # CA 9: LUỒNG KHỞI TẠO RẠCH RÒI CASE A VÀ CASE B
    # =========================================================================
    def test_case_9_initialization_flow_and_clean_state(self):
        """Kiểm tra:
        - Hệ thống chưa có PIN và Tên bé là Case A (is_initialized = False)
        - Cấu hình lần đầu chuyển sang Case B (is_initialized = True)
        - Clean state reset đưa về Case A sạch sẽ
        """
        from app.routers.policy_events import get_auth_settings, reset_system_state

        # 1. Reset về trạng thái sạch (Case A)
        res_reset = reset_system_state(db=self.db)
        self.assertEqual(res_reset["status"], "success")

        # 2. Kiểm tra Case A: Chưa có PIN và Tên bé
        status_a = get_auth_settings(child_id=1, db=self.db)
        self.assertFalse(status_a["is_initialized"], "Hệ thống mới phải có is_initialized = False")
        self.assertFalse(status_a["has_pin"], "Hệ thống mới chưa có PIN")
        self.assertEqual(status_a["child_name"], "", "Hệ thống mới Tên bé phải là rỗng, không được hardcode Bé An")

        # 3. Phụ huynh khởi tạo lần đầu: Tên 'Bé Bo', PIN '8888'
        policy = self.db.query(Policy).filter(Policy.child_id == 1).first()
        policy.child_name = "Bé Bo"
        policy.lock_pin = "8888"
        self.db.commit()

        # 4. Kiểm tra Case B: Đã có PIN và Tên bé
        status_b = get_auth_settings(child_id=1, db=self.db)
        self.assertTrue(status_b["is_initialized"], "Sau khởi tạo phải chuyển sang Case B (is_initialized = True)")
        self.assertTrue(status_b["has_pin"])
        self.assertEqual(status_b["child_name"], "Bé Bo")

        # 5. Dọn dẹp trả về Clean State ban đầu (Case A) để phục vụ chạy ứng dụng thật
        reset_system_state(db=self.db)
        status_clean = get_auth_settings(child_id=1, db=self.db)
        self.assertFalse(status_clean["is_initialized"])
        self.assertEqual(status_clean["child_name"], "")
        self.assertEqual(status_clean["lock_pin"], "")


if __name__ == "__main__":
    unittest.main()
