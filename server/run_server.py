#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Entry point khởi chạy OGK Server (Web Dashboard & Backend API).
Hỗ trợ chạy trực tiếp bằng python hoặc đóng gói PyInstaller thành server.exe.
"""

import os
import sys
import uvicorn

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    if sys._MEIPASS not in sys.path:
        sys.path.insert(0, sys._MEIPASS)

from app.main import app

def main():
    print("=" * 65)
    print("  OGK SERVER - MÁY CHỦ BẢO VỆ THIẾT BỊ TRẺ EM")
    print("  Dashboard Quản trị: http://127.0.0.1:8000")
    print("  Nhấn Ctrl + C để dừng máy chủ an toàn.")
    print("=" * 65)
    uvicorn.run(
        app, host="127.0.0.1", port=8000, log_level="info",
        ws="websockets-sansio", ws_ping_interval=5, ws_ping_timeout=5,
    )

if __name__ == "__main__":
    main()

