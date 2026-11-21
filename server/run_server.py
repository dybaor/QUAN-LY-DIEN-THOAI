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

for _stream in (sys.stdout, sys.stderr):
    if _stream and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")  # Banner tiếng Việt khi ghi log ra file

from app.main import app

def main():
    host = os.environ.get("OGK_HOST", "127.0.0.1")
    port = int(os.environ.get("OGK_PORT", "8000"))
    certfile = os.environ.get("OGK_SSL_CERTFILE")
    keyfile = os.environ.get("OGK_SSL_KEYFILE")
    scheme = "https" if certfile else "http"
    if host not in ("127.0.0.1", "localhost") and not certfile:
        sys.exit("Từ chối chạy trên mạng không có TLS. Hãy đặt OGK_SSL_CERTFILE và OGK_SSL_KEYFILE.")
    print("=" * 65)
    print("  OGK SERVER - MÁY CHỦ BẢO VỆ THIẾT BỊ TRẺ EM")
    print(f"  Dashboard Quản trị: {scheme}://{host}:{port}")
    print("  Nhấn Ctrl + C để dừng máy chủ an toàn.")
    print("=" * 65)
    tls = {}
    if certfile:
        import ssl
        tls = {"ssl_certfile": certfile, "ssl_keyfile": keyfile, "ssl_version": ssl.PROTOCOL_TLS_SERVER}
    uvicorn.run(
        app, host=host, port=port, log_level="info",
        ws="websockets-sansio", ws_ping_interval=5, ws_ping_timeout=5, **tls,
    )

if __name__ == "__main__":
    main()

