#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit test kiểm chứng:
1. Cơ chế khóa cô lập trong cửa sổ (In-App Lock Overlay) TUYỆT ĐỐI không gọi LockWorkStation của Windows.
2. Cơ chế chặn tên miền (Domain Interception) trong Safe Browser nội bộ, không rò rỉ ra webbrowser ngoài.
3. Trừ giờ thời gian thực và tự động khóa khi hết hạn mức.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

# Đảm bảo đường dẫn import
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_DIR = os.path.join(BASE_DIR, "agent")
for p in [BASE_DIR, AGENT_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from agent.safe_browser import (
        extract_domain,
        is_domain_blocked,
        render_blocked_html,
        open_safe_browser
    )
    from agent.blocker import blocker
except ImportError:
    from safe_browser import (  # type: ignore
        extract_domain,
        is_domain_blocked,
        render_blocked_html,
        open_safe_browser
    )
    from blocker import blocker  # type: ignore


class TestSafeLockAndWeb(unittest.TestCase):

    def test_domain_interception_allowed_and_blocked(self):
        """Kiểm tra Safe Browser chặn chính xác các domain cấm và cho phép domain học tập."""
        # Domain hợp lệ
        is_b_google, _ = is_domain_blocked("https://www.google.com/searchtoan+lop+5")
        self.assertFalse(is_b_google, "Google phải được cho phép")

        is_b_wiki, _ = is_domain_blocked("https://vi.wikipedia.org/wiki/Viet_Nam")
        self.assertFalse(is_b_wiki, "Wikipedia phải được cho phép")

        is_b_scratch, _ = is_domain_blocked("https://scratch.mit.edu")
        self.assertFalse(is_b_scratch, "Scratch phải được cho phép")

        # Domain cấm (Giải trí, mạng xã hội, web đen)
        is_b_yt, r_yt = is_domain_blocked("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertTrue(is_b_yt, "YouTube phải bị chặn")
        self.assertIn("youtube.com", r_yt.lower())

        is_b_fb, r_fb = is_domain_blocked("https://m.facebook.com")
        self.assertTrue(is_b_fb, "Facebook phải bị chặn")

        is_b_tt, r_tt = is_domain_blocked("https://www.tiktok.com/@trending")
        self.assertTrue(is_b_tt, "TikTok phải bị chặn")

    def test_open_safe_browser_keeps_in_app_no_external_escape(self):
        """Kiểm tra open_safe_browser hoạt động nội bộ, render HTML cảnh báo khi gặp link cấm."""
        with patch("webbrowser.open") as mock_wb, patch("os.startfile", create=True) as mock_sf:
            # Truy cập domain cấm
            is_blocked, domain, reason = open_safe_browser("https://youtube.com", gui=False)
            self.assertTrue(is_blocked, "Phải nhận diện domain bị chặn")
            self.assertEqual(domain, "youtube.com")
            self.assertIn("youtube.com", reason.lower())

            # Tuyệt đối không được kích hoạt trình duyệt bên ngoài
            mock_wb.assert_not_called()
            mock_sf.assert_not_called()

            # Render HTML cảnh báo an toàn
            html = render_blocked_html("https://youtube.com", domain, reason)
            self.assertIn("TRANG WEB ĐÃ BỊ HẠN CHẾ", html)
            self.assertIn("youtube.com", html)

    def test_blocker_lock_workstation_does_not_call_user32_lock(self):
        """Kiểm tra blocker.lock_workstation không gọi ctypes.windll.user32.LockWorkStation."""
        with patch("ctypes.windll.user32.LockWorkStation", side_effect=AssertionError("LockWorkStation must NOT be called!")):
            res = blocker.lock_workstation("Lệnh thử nghiệm từ phụ huynh")
            self.assertTrue(res, "Hàm phải trả về True sau khi ghi log sự kiện")

    def test_agent_service_initialization_no_index_error(self):
        """Kiểm tra khởi tạo Agent Service với args=None hoặc args=[] không bị lỗi IndexError list index out of range."""
        from agent.main_service import OGKChildAgentService

        # Khởi tạo không truyền args
        svc1 = OGKChildAgentService()
        self.assertTrue(svc1.is_running)

        # Khởi tạo truyền args rỗng []
        svc2 = OGKChildAgentService([])
        self.assertTrue(svc2.is_running)

    def test_websocket_manager_multiple_connections_sync(self):
        """Kiểm tra ConnectionManager quản lý danh sách đa kết nối đồng thời trên cùng device_id."""
        from unittest.mock import MagicMock
        from server.app.websocket_manager import ConnectionManager

        mgr = ConnectionManager()
        ws_agent = MagicMock()
        ws_child = MagicMock()

        # Thêm thủ công 2 kết nối cho cùng 1 device_id
        mgr.active_connections["DEVICE-01"].add(ws_agent)
        mgr.active_connections["DEVICE-01"].add(ws_child)
        self.assertEqual(len(mgr.active_connections["DEVICE-01"]), 2)

        # Ngắt kết nối 1 client, kết nối còn lại vẫn duy trì
        mgr.disconnect("DEVICE-01", ws_agent)
        self.assertEqual(len(mgr.active_connections["DEVICE-01"]), 1)
        self.assertIn(ws_child, mgr.active_connections["DEVICE-01"])

        # Ngắt kết nối nốt client thứ 2 -> device_id được dọn dẹp sạch
        mgr.disconnect("DEVICE-01", ws_child)
        self.assertNotIn("DEVICE-01", mgr.active_connections)

    def test_proxy_web_endpoint_and_onboarding_elements(self):
        """Kiểm tra endpoint /proxy/web và các thành phần Onboarding Gate + Smooth Scrollbar."""
        try:
            from starlette.requests import Request  # type: ignore
        except ImportError:
            Request = None  # type: ignore
        from server.app.main import proxy_web, serve_dashboard

        self.assertEqual(proxy_web("https://example.com").status_code, 403)

        # 3. Test dashboard HTML layout, quick actions menu, and onboarding modal
        req = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
        res_dashboard = serve_dashboard(req)
        self.assertEqual(res_dashboard.status_code, 200)
        html = res_dashboard.body.decode("utf-8")
        self.assertIn("onboardingModal", html)
        self.assertIn("leftDashboardCol", html)
        self.assertIn("rightDashboardCol", html)
        self.assertIn("btnQuickActions", html)
        self.assertIn("quickActionsMenu", html)
        self.assertIn("Thời gian biểu hoạt động", html)
        self.assertNotIn("Daily Quotas", html)
        self.assertNotIn("navigator.mediaDevices", html, "Parent dashboard must never call navigator.mediaDevices")
        self.assertNotIn("getDisplayMedia", html, "Parent dashboard must never call getDisplayMedia")

    def test_child_js_screen_share_and_proxy_options(self):
        """Kiểm tra cấu hình child.js có preferCurrentTab: true, toBlob binary streaming 15-30 FPS, flow control bufferedAmount, init_completed và proxy cho web apps."""
        child_js_path = os.path.join(BASE_DIR, "server", "static", "js", "child.js")
        with open(child_js_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('preferCurrentTab: true', content)
        self.assertIn('selfBrowserSurface: "include"', content)
        self.assertNotIn('/proxy/web?url=', content)
        self.assertIn('bufferedAmount', content)
        self.assertIn('toBlob', content)
        self.assertIn('image/jpeg', content)
        self.assertIn('800', content)
        self.assertIn('init_completed', content)
        self.assertIn('checkInitializationStatus', content)

    def test_zero_hardcoded_pin_and_neutral_placeholder(self):
        """Kiểm tra tuyệt đối không còn hardcode 1234/0000 trong child.js và không còn gợi ý mã PIN trên giao diện khóa."""
        child_js_path = os.path.join(BASE_DIR, "server", "static", "js", "child.js")
        with open(child_js_path, "r", encoding="utf-8") as f:
            child_js = f.read()

        self.assertNotIn("pin === '1234'", child_js)
        self.assertNotIn('pin === "1234"', child_js)
        self.assertNotIn("pin === '0000'", child_js)
        self.assertNotIn('pin === "0000"', child_js)
        self.assertIn('configuredParentPin = ""', child_js)

        child_portal_path = os.path.join(BASE_DIR, "server", "templates", "child_portal.html")
        with open(child_portal_path, "r", encoding="utf-8") as f:
            portal_html = f.read()

        self.assertNotIn("1234", portal_html)
        self.assertIn('placeholder="Nhập mã PIN của phụ huynh..."', portal_html)
        self.assertIn('type="password"', portal_html)

    def test_realtime_chat_and_violation_alert(self):
        """Kiểm tra tính năng Chat xuyên suốt, Cảnh báo vi phạm thời gian thực."""
        # 1. Kiểm tra Trang con (child_portal.html)
        child_portal_path = os.path.join(BASE_DIR, "server", "templates", "child_portal.html")
        with open(child_portal_path, "r", encoding="utf-8") as f:
            portal_html = f.read()

        self.assertTrue('id="floatingChatWindow"' in portal_html or 'id="childChatWidget"' in portal_html)
        self.assertTrue('id="floatingChatBtn"' in portal_html or 'id="btnChildChatToggle"' in portal_html)
        self.assertNotIn('id="mockAppModal"', portal_html)
        self.assertIn('id="violationBlockModal"', portal_html)
        self.assertIn('toggleChildChat', portal_html)

        # 2. Kiểm tra JavaScript trang con (child.js)
        child_js_path = os.path.join(BASE_DIR, "server", "static", "js", "child.js")
        with open(child_js_path, "r", encoding="utf-8") as f:
            child_js = f.read()

        self.assertIn('reportBlockedSearch', child_js)
        self.assertIn('showViolationBlockModal', child_js)
        self.assertIn('sendChildChatMessage', child_js)
        self.assertIn('violation_alert', child_js)
        self.assertIn('chat_message', child_js)

        # 3. Kiểm tra Dashboard Phụ huynh (dashboard.html & index.html)
        for filename in ["dashboard.html", "index.html"]:
            tmpl_path = os.path.join(BASE_DIR, "server", "templates", filename)
            with open(tmpl_path, "r", encoding="utf-8") as f:
                dash_html = f.read()

            self.assertIn('id="parentChatMessageList"', dash_html)
            self.assertIn('id="parentChatInput"', dash_html)
            self.assertIn('id="realtimeViolationModal"', dash_html)
            self.assertIn('violation_alert', dash_html)
            self.assertIn('sendParentChatMessage', dash_html)

    def test_parent_dashboard_binary_screen_handling(self):
        """Kiểm tra Parent Dashboard (dashboard.html & index.html) hỗ trợ nhận Binary Blob và tự giải phóng revokeObjectURL."""
        for filename in ["dashboard.html", "index.html"]:
            tmpl_path = os.path.join(BASE_DIR, "server", "templates", filename)
            with open(tmpl_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("parentWs.binaryType = 'blob'", content)
            self.assertIn("URL.createObjectURL(blob)", content)
            self.assertIn("URL.revokeObjectURL(oldUrl)", content)
            self.assertIn("15 - 30 FPS", content)

    def test_child_portal_waiting_screen_element(self):
        """Kiểm tra màn hình chờ khởi tạo (waitingScreenState) tồn tại trong child_portal.html."""
        child_portal_path = os.path.join(BASE_DIR, "server", "templates", "child_portal.html")
        with open(child_portal_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('id="waitingScreenState"', content)
        self.assertIn('Đang kết nối với phụ huynh...', content)

    def test_connection_manager_targeted_sending(self):
        """Kiểm tra ConnectionManager hỗ trợ gửi riêng biệt tới children hoặc parents và gửi binary bytes."""
        import inspect
        from server.app.websocket_manager import ConnectionManager

        mgr = ConnectionManager()
        mock_child = MagicMock()
        mock_parent = MagicMock()

        mgr.active_connections["child_abc"].add(mock_child)
        mgr.active_connections["parent_xyz"].add(mock_parent)

        children_keys = [k for k in mgr.active_connections.keys() if str(k).startswith("child_")]
        parents_keys = [k for k in mgr.active_connections.keys() if str(k).startswith("parent_")]
        self.assertEqual(children_keys, ["child_abc"])
        self.assertEqual(parents_keys, ["parent_xyz"])
        self.assertTrue(hasattr(mgr, "send_to_children"))
        self.assertTrue(hasattr(mgr, "send_to_parents"))
        self.assertTrue(hasattr(mgr, "send_bytes_to_parents"))
        self.assertTrue(inspect.iscoroutinefunction(mgr.send_bytes_to_parents))


    def test_total_lock_time_expired_and_no_external_tabs(self):
        """Kiểm tra:
        1. child_portal.html không chứa bất kỳ target="_blank" nào.
        2. child.js không chứa Zing MP3 hay Duolingo trong APPS.
        3. Cơ chế isTimeExpired, handleTimeExpired, pointer-events disable khi hết giờ.
        4. Modal timeExpiredAlertModal và WebSocket time_expired_alert trên Parent Dashboard.
        """
        # 1. Kiểm tra child_portal.html
        portal_path = os.path.join(BASE_DIR, "server", "templates", "child_portal.html")
        with open(portal_path, "r", encoding="utf-8") as f:
            portal_html = f.read()

        self.assertNotIn('target="_blank"', portal_html, "child_portal.html không được chứa target=_blank")
        self.assertNotIn('btnOpenExternalWeb', portal_html, "Nút Mở tab riêng phải bị xóa bỏ")
        self.assertNotIn('Duolingo', portal_html, "Không được gợi ý Duolingo trong search placeholder")

        # 2. Kiểm tra child.js
        child_js_path = os.path.join(BASE_DIR, "server", "static", "js", "child.js")
        with open(child_js_path, "r", encoding="utf-8") as f:
            child_js = f.read()

        self.assertNotIn("'zingmp3'", child_js, "Zing MP3 phải bị xóa khỏi APPS")
        self.assertNotIn("'duolingo'", child_js, "Duolingo phải bị xóa khỏi APPS")
        self.assertIn("isTimeExpired", child_js)
        self.assertIn("handleTimeExpired", child_js)
        self.assertIn("disableAppInteractions", child_js)
        self.assertIn("time_expired_alert", child_js)
        self.assertNotIn("window.open(", child_js, "Không được dùng window.open")

        # 3. Kiểm tra Parent Dashboard
        for filename in ["dashboard.html", "index.html"]:
            dash_path = os.path.join(BASE_DIR, "server", "templates", filename)
            with open(dash_path, "r", encoding="utf-8") as f:
                dash_html = f.read()

            self.assertIn('id="timeExpiredAlertModal"', dash_html)
            self.assertIn('time_expired_alert', dash_html)
            self.assertIn('approveTimeExtensionFromAlert', dash_html)
            self.assertIn('updateDeviceStatusToTimeExpired', dash_html)

    def test_clean_lock_overlay_and_google_search_moderation(self):
        """Kiểm tra:
        1. Xóa nút chat dư thừa bên trong #lockOverlay, giữ lại floating chat button z-index cao.
        2. Đồng hồ và trạng thái thời gian trên #lockOverlay.
        3. Thanh tìm kiếm Google tích hợp kiểm duyệt (placeholder, nút tìm kiếm, Enter key).
        4. Logic handleGoogleOrDomainSearch, extractDomain, isDomainBlocked trong child.js.
        """
        portal_path = os.path.join(BASE_DIR, "server", "templates", "child_portal.html")
        with open(portal_path, "r", encoding="utf-8") as f:
            portal_html = f.read()

        # 1. Trích xuất nội dung của #lockOverlay
        lock_overlay_start = portal_html.find('<div id="lockOverlay">')
        lock_overlay_end = portal_html.find('</div>\n    </div>', lock_overlay_start)
        lock_overlay_content = portal_html[lock_overlay_start:lock_overlay_end + 15]

        # Xác nhận không có nút chat nào bên trong #lockOverlay
        self.assertNotIn("openChildChatBox()", lock_overlay_content, "#lockOverlay không được chứa nút chat trùng lặp")
        self.assertNotIn("Nhắn tin trò chuyện với Ba Mẹ", lock_overlay_content)

        # Xác nhận có đồng hồ và hiển thị thời gian kết thúc
        self.assertIn('id="lockOverlayClock"', lock_overlay_content)
        self.assertIn('id="lockOverlayTimeStatus"', lock_overlay_content)

        # Xác nhận floating chat button vẫn tồn tại với z-index vượt trên lockOverlay
        self.assertTrue('id="floatingChatBtn"' in portal_html or 'id="btnChildChatToggle"' in portal_html)
        self.assertTrue('z-index: 9998' in portal_html or 'z-[100005]' in portal_html or 'z-9998' in portal_html)

        # 2. Kiểm tra thanh tìm kiếm và placeholder
        self.assertIn('placeholder="Tìm kiếm trên Google…"', portal_html)
        self.assertIn('aria-label="Tìm kiếm trên Google"', portal_html)
        self.assertIn('id="btnSearchGoogle"', portal_html)
        self.assertIn('handleGoogleOrDomainSearch()', portal_html)

        # 3. Kiểm tra child.js
        child_js_path = os.path.join(BASE_DIR, "server", "static", "js", "child.js")
        with open(child_js_path, "r", encoding="utf-8") as f:
            child_js = f.read()

        self.assertIn("function handleGoogleOrDomainSearch(", child_js)
        self.assertIn("function extractDomain(", child_js)
        self.assertIn("function isDomainBlocked(", child_js)
        self.assertIn("igu=1", child_js, "Google search URL phải chứa tham số nhúng igu=1")
        self.assertIn("https://www.google.com/search", child_js)
        self.assertIn("reportBlockedSearch(", child_js)
        self.assertIn("showViolationBlockModal(", child_js)

    def test_restricted_keywords_filter_and_strict_safesearch(self):
        """Kiểm tra:
        1. child.js định nghĩa RESTRICTED_KEYWORDS và hàm checkRestrictedKeyword.
        2. Google Search cưỡng chế đính kèm safe=active, ssui=on và igu=1.
        3. Phản hồi cảnh báo nội bộ 'query_filter' và bắn violation_alert lên server.
        4. Endpoint /events/violations/{child_id} trong policy_events.py hỗ trợ query_filter.
        """
        child_js_path = os.path.join(BASE_DIR, "server", "static", "js", "child.js")
        with open(child_js_path, "r", encoding="utf-8") as f:
            child_js = f.read()

        # 1. Kiểm tra cấu hình từ khóa hạn chế
        self.assertIn("RESTRICTED_KEYWORDS", child_js)
        self.assertIn("function checkRestrictedKeyword(", child_js)
        self.assertIn("function removeVietnameseTones(", child_js)

        # 2. Kiểm tra cờ SafeSearch bắt buộc
        self.assertIn("search.searchParams.set('safe', 'active')", child_js)
        self.assertIn("safe: 'active'", child_js)
        self.assertIn("query_filter", child_js)

        # 3. Kiểm tra thông báo nội bộ
        self.assertIn("Nội dung tìm kiếm chứa từ khóa không phù hợp với quy định của phụ huynh!", child_js)

        # 4. Kiểm tra backend policy_events.py
        from server.app.routers.policy_events import get_violation_events
        import inspect
        sig = inspect.signature(get_violation_events)
        self.assertIn("child_id", sig.parameters)

    def test_toast_singleton_glassmorphism_chat_and_modal_close_buttons(self):
        """Kiểm tra:
        1. Toast Singleton pattern (2500ms auto-dismiss, container.innerHTML = '')
        2. Widget Chat nổi Dark Glassmorphism ở cả Dashboard Phụ huynh và Child Portal
        3. Khung màn hình giám sát Clean UI (có nút 'Xem màn hình', không subtitle rườm rà)
        4. Tất cả modals đều có nút đóng [✕] và hỗ trợ Escape / Backdrop click.
        """
        # 1. Kiểm tra child.js và child_portal.html
        child_portal_path = os.path.join(BASE_DIR, "server", "templates", "child_portal.html")
        with open(child_portal_path, "r", encoding="utf-8") as f:
            portal_html = f.read()

        child_js_path = os.path.join(BASE_DIR, "server", "static", "js", "child.js")
        with open(child_js_path, "r", encoding="utf-8") as f:
            child_js = f.read()

        # Child Toast Singleton
        self.assertIn("childToastTimeout", child_js)
        self.assertIn("2500", child_js)
        self.assertIn("container.innerHTML = ''", child_js)

        # Child Floating Chat Glassmorphism
        self.assertIn('id="floatingChatBtn"', portal_html)
        self.assertIn('id="floatingChatWindow"', portal_html)
        self.assertIn('id="childChatUnreadBadge"', portal_html)

        # Child Modals have close buttons
        self.assertIn('closeViolationBlockModal()', portal_html)
        self.assertIn('respondScreenConsent(false)', portal_html)

        # Kiểm tra child.css z-index hierarchy
        child_css_path = os.path.join(BASE_DIR, "server", "static", "css", "child.css")
        with open(child_css_path, "r", encoding="utf-8") as f:
            child_css = f.read()
        self.assertIn("z-index: 9990;", child_css)

        # 2. Kiểm tra parent dashboard (dashboard.html & index.html)
        for filename in ["dashboard.html", "index.html"]:
            tmpl_path = os.path.join(BASE_DIR, "server", "templates", filename)
            with open(tmpl_path, "r", encoding="utf-8") as f:
                dash_html = f.read()

            # Parent Toast Singleton
            self.assertIn("parentToastTimeout", dash_html)
            self.assertIn("2500", dash_html)
            self.assertIn("container.innerHTML = ''", dash_html)

            # Parent Floating Chat
            self.assertIn('id="floatingChatBtn"', dash_html)
            self.assertIn('id="floatingChatWindow"', dash_html)
            self.assertIn('id="parentChatUnreadBadge"', dash_html)
            self.assertIn('toggleParentChat()', dash_html)

            # Live screen clean UI
            self.assertIn('<span>Xem màn hình</span>', dash_html)
            self.assertNotIn('Chưa kết nối màn hình của bé', dash_html)

            # Modals have top-right close buttons
            self.assertIn('closeRealtimeViolationModal()', dash_html)
            self.assertIn('closeTimeExpiredAlertModal()', dash_html)
            self.assertIn('closeOnboardingModal()', dash_html)


if __name__ == "__main__":
    unittest.main()

