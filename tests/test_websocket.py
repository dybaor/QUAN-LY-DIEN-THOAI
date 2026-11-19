#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ca kiểm thử đồng bộ cho WebSocket Connection Manager:
- Đăng ký và quản lý thiết bị trực tuyến
- Quản lý danh sách kết nối an toàn không phụ thuộc event loop
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

BASE_DIR = Path(__file__).resolve().parent.parent
SERVER_DIR = BASE_DIR / "server"
for p in [str(BASE_DIR), str(SERVER_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from server.app.websocket_manager import ConnectionManager
except ImportError:
    from app.websocket_manager import ConnectionManager  # type: ignore


class TestWebSocket(unittest.TestCase):

    def test_websocket_connection_and_command(self):
        """Kiểm tra quản lý kết nối và danh sách thiết bị trực tuyến."""
        mgr = ConnectionManager()
        test_device_id = "TEST-DEVICE-GUID-12345"
        mock_ws = MagicMock()

        # 1. Đăng ký kết nối
        mgr.active_connections[test_device_id].add(mock_ws)
        self.assertIn(test_device_id, mgr.active_connections)
        self.assertEqual(len(mgr.active_connections[test_device_id]), 1)

        # 2. Ngắt kết nối
        mgr.disconnect(test_device_id, mock_ws)
        self.assertNotIn(test_device_id, mgr.active_connections)


if __name__ == "__main__":
    unittest.main()
