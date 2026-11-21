"""Gỡ cài đặt Agent hợp pháp (F4-MR1): bắt buộc tài khoản phụ huynh, ghi log cục bộ và audit log trên máy chủ."""

import datetime
import getpass
import os
import subprocess
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import requests

import settings
from local_cache import local_cache
from transport import AuthError, api

SERVICE_NAME = "OGKChildAgent"
TRAY_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def log(message: str):
    os.makedirs(os.path.join(settings.DATA_DIR, "logs"), exist_ok=True)
    with open(os.path.join(settings.DATA_DIR, "logs", "uninstall.log"), "a", encoding="utf-8") as handle:
        handle.write(f"[{datetime.datetime.now().isoformat()}] {message}\n")
    print(message)


def authorize() -> bool:
    if not local_cache.is_enrolled:
        log("Máy chưa ghép đôi — cho phép gỡ cài đặt.")
        return True
    for attempt in range(3):
        username = input("Tên đăng nhập phụ huynh: ").strip()
        password = getpass.getpass("Mật khẩu phụ huynh: ")
        try:
            resp = api.request("POST", "/enroll/uninstall-authorize", json={"username": username, "password": password})
        except AuthError:
            log("Thiết bị đã bị gỡ ghép đôi trên máy chủ — cho phép gỡ cài đặt.")
            return True
        except requests.RequestException as exc:
            log(f"Không kết nối được máy chủ OGK ({exc}). Cần có kết nối để xác thực phụ huynh.")
            return False
        if resp.status_code == 200:
            log(f"Phụ huynh '{username}' đã xác thực gỡ cài đặt.")
            return True
        log(f"Xác thực thất bại (lần {attempt + 1}/3).")
    return False


def remove_everything():
    subprocess.run(["sc", "stop", SERVICE_NAME], capture_output=True)
    subprocess.run(["sc", "delete", SERVICE_NAME], capture_output=True)
    subprocess.run(["reg", "delete", rf"HKLM\{TRAY_RUN_KEY}", "/v", "OGKTray", "/f"], capture_output=True)
    local_cache.clear_identity()
    for name in ("agent_cache.db", "agent_cache.db-wal", "agent_cache.db-shm", "cache.key"):
        path = os.path.join(settings.DATA_DIR, name)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
    log("Đã gỡ dịch vụ OGKChildAgent, tự khởi động khay hệ thống và xóa bộ nhớ đệm.")


def run() -> int:
    if not authorize():
        log("Từ chối gỡ cài đặt.")
        return 1
    remove_everything()
    print("Biểu tượng khay sẽ biến mất sau khi đăng xuất hoặc khởi động lại máy.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
