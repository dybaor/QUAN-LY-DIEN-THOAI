#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
OGK SYSTEM - RELEASE & DEPLOYMENT BUILD SCRIPT (DevOps Automation)
Dự án: Người Bạn Đồng Hành (OGK - Child Device & Network Protection System)
Mục đích: Đóng gói toàn bộ Agent và DNS Proxy thành file thực thi (.exe) độc lập
          và tạo bộ kịch bản triển khai một chạm (deploy package) chuẩn Windows 10/11 x64.
================================================================================
"""

import os
import sys
import shutil
import subprocess
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "dist"
BUILD_DIR = BASE_DIR / "build"
PACKAGE_DIR = BASE_DIR / "dist_package"

# Nội dung các file kịch bản triển khai (.bat) và hướng dẫn (.txt)
INSTALL_SERVICE_BAT = r"""@echo off
chcp 65001 >nul
title [OGK-AGENT] Cai Dat Windows Service

echo ==============================================================================
echo [OGK-AGENT] KHOI TAO CAI DAT WINDOWS SERVICE: OGKChildAgent (LocalSystem)
echo ==============================================================================

:: 1. Kiem tra quyen Administrator
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] BAN PHAI CHAY FILE NAY VOI QUYEN "RUN AS ADMINISTRATOR"!
    echo         Click chuot phai vao file install_service.bat -^> chon "Run as administrator".
    echo ==============================================================================
    pause
    exit /b 1
)

:: 2. Kiem tra file thuc thi agent_service.exe
if not exist "%~dp0agent_service.exe" (
    echo [ERROR] Khong tim thay file "agent_service.exe" trong thu muc hien tai!
    echo         Vui long kiem tra lai bo cai dat.
    echo ==============================================================================
    pause
    exit /b 1
)

:: 3. Tao thu muc luu tru du lieu %ProgramData%\OGKAgent va phan quyen
set AGENT_DATA=%ProgramData%\OGKAgent
if not exist "%AGENT_DATA%" (
    mkdir "%AGENT_DATA%"
)
if not exist "%AGENT_DATA%\logs" (
    mkdir "%AGENT_DATA%\logs"
)
icacls "%AGENT_DATA%" /inheritance:r /grant:r "NT AUTHORITY\SYSTEM":(OI)(CI)F /grant:r "BUILTIN\Administrators":(OI)(CI)F >nul 2>&1

:: 4. Dung va xoa phien ban cu cua dich vu neu dang ton tai
echo [INFO] Kiem tra va go bo phien ban cu neu co...
net stop OGKChildAgent >nul 2>&1
sc stop OGKChildAgent >nul 2>&1
sc delete OGKChildAgent >nul 2>&1
timeout /t 2 /nobreak >nul

:: 5. Dang ky dich vu Windows moi chay duoi quyen LocalSystem
echo [INFO] Dang dang ky dich vu Windows: OGKChildAgent...
sc create "OGKChildAgent" binPath= "\"%~dp0agent_service.exe\"" start= auto DisplayName= "OGK Child Monitoring Agent" obj= LocalSystem
if %errorlevel% neq 0 (
    echo [ERROR] Dang ky dich vu that bai!
    pause
    exit /b 1
)

:: 6. Dat mo ta cho dich vu
sc description "OGKChildAgent" "He thong quan ly thoi gian su dung thiet bi cho tre em (Do an Nguoi Ban Dong Hanh). Theo doi tien trinh, dem gio, chan ung dung va dong bo chinh sach." >nul 2>&1

:: 7. Cau hinh co che tu dong khoi phuc khi crash sau 5 giay (Tieu chuan Chuyen de M5)
echo [INFO] Cau hinh Recovery Options (Tu dong Restart sau 5 giay khi Service gap su co)...
sc failure "OGKChildAgent" reset= 86400 actions= restart/5000/restart/5000/restart/5000

:: 8. Khoi chay dich vu
echo [INFO] Dang khoi dong dich vu OGKChildAgent...
sc start OGKChildAgent
timeout /t 2 /nobreak >nul

:: 9. Kiem tra trang thai va bao cao ket qua
echo.
echo ==============================================================================
echo [THONG TIN CAU HINH PHUC HOI M5]
sc qfailure OGKChildAgent
echo ==============================================================================
echo [TRANG THAI HOAT DONG DICH VU]
sc query OGKChildAgent
echo ==============================================================================
echo [SUCCESS] DICH VU OGKChildAgent DA DUOC CAI DAT VA KHOI DONG THANH CONG!
echo           Dich vu se tu dong khoi dong cung Windows va chay ngam LocalSystem.
echo ==============================================================================
pause
"""

UNINSTALL_SERVICE_BAT = r"""@echo off
chcp 65001 >nul
title [OGK-AGENT] Go Bo Windows Service

echo ==============================================================================
echo [OGK-AGENT] GO BO DICH VU: OGKChildAgent
echo ==============================================================================

:: 1. Kiem tra quyen Administrator
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] BAN PHAI CHAY FILE NAY VOI QUYEN "RUN AS ADMINISTRATOR"!
    echo         Click chuot phai vao file uninstall_service.bat -^> chon "Run as administrator".
    echo ==============================================================================
    pause
    exit /b 1
)

:: 2. Dung dich vu
echo [INFO] Dang dung dich vu OGKChildAgent...
net stop OGKChildAgent >nul 2>&1
sc stop OGKChildAgent >nul 2>&1

:: 3. Xoa dich vu khoi Windows Service Manager
echo [INFO] Dang xoa dich vu khoi he thong...
sc delete OGKChildAgent
if %errorlevel% equ 0 (
    echo [SUCCESS] Da go bo dich vu OGKChildAgent thanh cong!
) else (
    echo [WARNING] Dich vu khong ton tai hoac da duoc go bo truoc do.
)

echo ==============================================================================
pause
"""

START_PROXY_BAT = r"""@echo off
chcp 65001 >nul
title [OGK-PROXY] DNS Proxy Server (Port 53)

echo ==============================================================================
echo [OGK-PROXY] KHOI CHAY DNS PROXY SERVER (UDP 127.0.0.1:53)
echo ==============================================================================

:: 1. Kiem tra quyen Administrator (Bat buoc de lang nghe Port 53)
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] BAN PHAI CHAY FILE NAY VOI QUYEN "RUN AS ADMINISTRATOR"!
    echo         Viec mo cong UDP 53 tren Windows yeu cau dac quyen Quan tri vien.
    echo         Click chuot phai vao start_proxy.bat -^> chon "Run as administrator".
    echo ==============================================================================
    pause
    exit /b 1
)

:: 2. Kiem tra file dns_proxy.exe
if not exist "%~dp0dns_proxy.exe" (
    echo [ERROR] Khong tim thay file "dns_proxy.exe" trong thu muc hien tai!
    pause
    exit /b 1
)

:: 3. Chuyen den thu muc chua file va thuc thi
cd /d "%~dp0"
echo [INFO] Dang khoi chay DNS Proxy Server...
echo [INFO] Nhan Ctrl + C de dung tien trinh.
echo ==============================================================================
"%~dp0dns_proxy.exe"

pause
"""

START_APP_BAT = r"""@echo off
chcp 65001 >nul
title [OGK-SYSTEM] KHOI CHAY TRON GOI (1-CLICK LAUNCHER)

echo ==============================================================================
echo [OGK-SYSTEM] KHOI CHAY TRON GOI 1-CLICK (ZERO TERMINAL - 100% WEB APP)
echo ==============================================================================

cd /d "%~dp0"

:: 1. Khoi dong Server Web Dashboard ngam
echo [1/3] Dang khoi dong OGK Server (Web Dashboard & API)...
if exist "%~dp0ogk_server.exe" (
    start "OGK-Server" /min "%~dp0ogk_server.exe"
) else (
    echo [ERROR] Khong tim thay ogk_server.exe!
)

:: 2. Cho server san sang va mo 2 tab trinh duyet Web: Phu huynh va Tre em
echo [2/3] Dang ket noi Dashboard: http://127.0.0.1:8000 va http://127.0.0.1:8000/child...
timeout /t 3 /nobreak >nul
start http://127.0.0.1:8000
start http://127.0.0.1:8000/child

:: 3. Khoi chay Agent giam sat ngam (Headless Background Daemon)
echo [3/3] Dang khoi dong Agent giam sat may con (Chay ngam hoan toan)...
if exist "%~dp0agent_service.exe" (
    start "OGK-Agent" /min "%~dp0agent_service.exe" debug
) else (
    echo [ERROR] Khong tim thay agent_service.exe!
)

echo.
echo ==============================================================================
echo [SUCCESS] TOAN BO HE THONG DA DUOC KHOI CHAY THANH CONG (100% WEB APP)!
echo           - Dashboard Phu huynh: http://127.0.0.1:8000 (Tab 1)
echo           - Cua so Web Tre em:   http://127.0.0.1:8000/child (Tab 2)
echo           - Agent Giam sat:      Dang chay ngam hoan toan (Chan app SHA-256)
echo           - De tat toan bo he thong khi dung xong: Chay file Stop_App.bat.
echo ==============================================================================
timeout /t 5 >nul
"""

STOP_APP_BAT = r"""@echo off
chcp 65001 >nul
title [OGK-SYSTEM] DUNG TOAN BO HE THONG

echo ==============================================================================
echo [OGK-SYSTEM] DANG DUNG TOAN BO TIEN TRINH (SERVER, AGENT, DNS PROXY)...
echo ==============================================================================

taskkill /F /IM ogk_server.exe >nul 2>&1
taskkill /F /IM agent_service.exe >nul 2>&1
taskkill /F /IM dns_proxy.exe >nul 2>&1
taskkill /F /IM child_client.exe >nul 2>&1

echo.
echo [SUCCESS] Da dung toan bo he thong OGK thanh cong!
echo ==============================================================================
timeout /t 3 >nul
"""

HUONG_DAN_CAI_DAT_TXT = """================================================================================
HƯỚNG DẪN TRIỂN KHAI VÀ SỬ DỤNG GÓI PHÁT HÀNH (DIST_PACKAGE)
Dự án: "Người Bạn Đồng Hành" (OGK Child Device & Network Protection System)
Thời gian triển khai: Dưới 5 phút | Không yêu cầu cài đặt Python
================================================================================

I. CẤU TRÚC GÓI PHÁT HÀNH (dist_package)
--------------------------------------------------------------------------------
├── agent_service.exe      : Ứng dụng Agent giám sát máy con (.exe độc lập, ẩn console)
├── dns_proxy.exe          : Máy chủ DNS Proxy cục bộ chặn tên miền độc hại (.exe độc lập)
├── blocklist.json         : Danh sách đen tên miền cấm (SafeSearch, DoH Canary, Web đen)
├── install_service.bat    : Script 1-Click cài đặt Windows Service chạy ngầm LocalSystem
├── start_proxy.bat        : Script 1-Click khởi chạy DNS Proxy lắng nghe cổng UDP 53
├── uninstall_service.bat  : Script 1-Click dừng và gỡ bỏ hoàn toàn Windows Service
└── HUONG_DAN_CAI_DAT.txt  : Tài liệu hướng dẫn sử dụng nhanh này

II. YÊU CẦU HỆ THỐNG
--------------------------------------------------------------------------------
- Hệ điều hành: Windows 10 hoặc Windows 11 (64-bit / x64).
- Quyền thực thi: Quyền Quản trị viên (Administrator) để tạo Windows Service và mở cổng mạng 53.
- KHÔNG CẦN CÀI ĐẶT PYTHON hay bất kỳ phần mềm phụ trợ nào khác.

III. CÁC BƯỚC CÀI ĐẶT NHANH (DƯỚI 5 PHÚT)
--------------------------------------------------------------------------------
1. CÀI ĐẶT VÀ KHỞI ĐỘNG AGENT GIÁM SÁT MÁY CON (AGENT SERVICE)
   Bước 1: Copy toàn bộ thư mục `dist_package` sang máy tính con cần giám sát
           (Ví dụ đặt tại: `C:\\OGKAgent\\`).
   Bước 2: Click chuột phải vào file `install_service.bat`.
   Bước 3: Chọn "Run as administrator" (Chạy với quyền Quản trị viên).
   Bước 4: Script sẽ tự động:
           + Tạo thư mục cơ sở dữ liệu đệm tại `%ProgramData%\\OGKAgent`.
           + Phân quyền bảo mật cao cho LocalSystem và Administrators.
           + Đăng ký Windows Service với tên `OGKChildAgent` chạy tự động khi bật máy.
           + Cấu hình cơ chế TỰ ĐỘNG KHỞI PHỤC SAU 5 GIÂY NẾU CRASH (Tiêu chuẩn M5).
           + Khởi chạy dịch vụ ngay lập tức.
   Bước 5: Màn hình hiển thị [SUCCESS] là bạn đã hoàn tất!

2. KHỞI CHẠY DNS PROXY CHẶN TRANG WEB ĐỘC HẠI & CƯỠNG CHẾ SAFESEARCH
   Bước 1: Click chuột phải vào file `start_proxy.bat`.
   Bước 2: Chọn "Run as administrator".
   Bước 3: Cửa sổ console sẽ hiện thông báo máy chủ đang lắng nghe tại UDP 127.0.0.1:53.
   Bước 4: Đổi DNS của Card mạng (Network Adapter) trên máy tính con:
           + Mở Control Panel -> Network and Sharing Center -> Change adapter settings.
           + Click chuột phải vào Wi-Fi hoặc Ethernet -> Properties.
           + Chọn "Internet Protocol Version 4 (TCP/IPv4)" -> Properties.
           + Chọn "Use the following DNS server addresses":
             Preferred DNS server: 127.0.0.1
             Alternate DNS server: 8.8.8.8
           + Nhấn OK để lưu.
   -> Mọi truy vấn tên miền cấm (Porn, Gambling, Violence, DoH Canary) sẽ bị Sinkhole về 0.0.0.0.

IV. CÁCH KIỂM TRA TRẠNG THÁI HOẠT ĐỘNG
--------------------------------------------------------------------------------
1. Kiểm tra qua Task Manager:
   - Mở Task Manager (Ctrl + Shift + Esc) -> Tab "Services" (Dịch vụ).
   - Tìm dịch vụ `OGKChildAgent` -> Trạng thái hiển thị là "Running".
2. Kiểm tra qua Services Manager:
   - Nhấn phím Windows + R -> Nhập `services.msc` -> Enter.
   - Tìm "OGK Child Monitoring Agent" -> Xem Recovery tab: "Restart the Service" sau 1 minute / 5 seconds.
3. Kiểm tra bằng Command Prompt / PowerShell (Run as Administrator):
   - Nhập lệnh: `sc query OGKChildAgent`
   - Nhập lệnh: `sc qfailure OGKChildAgent`
4. Kiểm tra Cơ sở dữ liệu Cache SQLite cục bộ:
   - File cache được lưu tại: `%ProgramData%\\OGKAgent\\agent_cache.db`
   - Đảm bảo hoạt động độc lập ngay cả khi mất kết nối mạng (Offline Resilience).

V. GỠ BỎ DỊCH VỤ (UNINSTALL)
--------------------------------------------------------------------------------
- Khi không còn nhu cầu giám sát hoặc muốn gỡ cài đặt sạch sẽ:
  Click chuột phải vào file `uninstall_service.bat` -> Chọn "Run as administrator".
  Dịch vụ `OGKChildAgent` sẽ tự động dừng và bị xóa hoàn toàn khỏi hệ điều hành Windows.

================================================================================
Chúc bạn triển khai thành công Hệ thống Quản lý "Người Bạn Đồng Hành" (OGK)!
================================================================================
"""


def log(msg: str, level: str = "INFO"):
    prefix = {
        "INFO": "[INFO]",
        "SUCCESS": "[SUCCESS]",
        "WARNING": "[WARNING]",
        "ERROR": "[ERROR]",
    }.get(level, "[INFO]")
    print(f"{prefix} {msg}")


def check_and_install_dependencies():
    """Kiểm tra và cài đặt pyinstaller cùng các thư viện cần thiết."""
    log("Kiểm tra môi trường Python và PyInstaller...")
    try:
        import PyInstaller
        log(f"Đã phát hiện PyInstaller phiên bản: {PyInstaller.__version__}", "SUCCESS")
    except ImportError:
        log("Chưa phát hiện PyInstaller. Đang tiến hành cài đặt tự động...", "WARNING")
        cmd = [sys.executable, "-m", "pip", "install", "pyinstaller"]
        subprocess.check_call(cmd)
        log("Đã cài đặt thành công PyInstaller!", "SUCCESS")


def build_agent_service(force: bool = False):
    """Biên dịch agent/main_service.py thành agent_service.exe."""
    log("=" * 70)
    log("1/4. ĐANG ĐÓNG GÓI AGENT MÁY CON (agent_service.exe)...")
    log("=" * 70)

    src_file = BASE_DIR / "agent" / "main_service.py"
    if not src_file.exists():
        raise FileNotFoundError(f"Không tìm thấy file nguồn: {src_file}")

    output_exe = DIST_DIR / "agent_service.exe"
    latest_src_mtime = max(f.stat().st_mtime for f in (BASE_DIR / "agent").glob("*.py"))
    if not force and output_exe.exists() and output_exe.stat().st_mtime > latest_src_mtime:
        size_mb = output_exe.stat().st_size / (1024 * 1024)
        log(f"Tái sử dụng bản build hiện có: {output_exe.name} ({size_mb:.2f} MB)", "SUCCESS")
        return

    cmd = [
        "pyinstaller",
        "--clean",
        "--noconfirm",
        "--onefile",
        "--noconsole",
        "--name", "agent_service",
        "--paths", str(BASE_DIR / "agent"),
        "--hidden-import=win32timezone",
        "--hidden-import=win32serviceutil",
        "--hidden-import=win32service",
        "--hidden-import=win32event",
        "--hidden-import=psutil",
        str(src_file),
    ]

    log(f"Thực thi lệnh: {' '.join(cmd)}")
    start_time = time.time()
    result = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        log(f"Lỗi khi build agent_service.exe:\n{result.stderr}", "ERROR")
        raise RuntimeError("Build agent_service.exe thất bại!")
    
    elapsed = time.time() - start_time
    output_exe = DIST_DIR / "agent_service.exe"
    if output_exe.exists():
        size_mb = output_exe.stat().st_size / (1024 * 1024)
        log(f"Đóng gói thành công: {output_exe.name} ({size_mb:.2f} MB) trong {elapsed:.1f}s", "SUCCESS")
    else:
        raise FileNotFoundError(f"Không tìm thấy file đích sau khi build: {output_exe}")


def build_dns_proxy(force: bool = False):
    """Biên dịch dns_proxy/proxy_server.py thành dns_proxy.exe."""
    log("=" * 70)
    log("2/4. ĐANG ĐÓNG GÓI DNS PROXY CỤC BỘ (dns_proxy.exe)...")
    log("=" * 70)

    src_file = BASE_DIR / "dns_proxy" / "proxy_server.py"
    if not src_file.exists():
        raise FileNotFoundError(f"Không tìm thấy file nguồn: {src_file}")

    output_exe = DIST_DIR / "dns_proxy.exe"
    latest_src_mtime = max(f.stat().st_mtime for f in (BASE_DIR / "dns_proxy").glob("*.*"))
    if not force and output_exe.exists() and output_exe.stat().st_mtime > latest_src_mtime:
        size_mb = output_exe.stat().st_size / (1024 * 1024)
        log(f"Tái sử dụng bản build hiện có: {output_exe.name} ({size_mb:.2f} MB)", "SUCCESS")
        return

    cmd = [
        "pyinstaller",
        "--clean",
        "--noconfirm",
        "--onefile",
        "--name", "dns_proxy",
        "--paths", str(BASE_DIR / "dns_proxy"),
        "--hidden-import=dnslib",
        str(src_file),
    ]

    log(f"Thực thi lệnh: {' '.join(cmd)}")
    start_time = time.time()
    result = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        log(f"Lỗi khi build dns_proxy.exe:\n{result.stderr}", "ERROR")
        raise RuntimeError("Build dns_proxy.exe thất bại!")

    elapsed = time.time() - start_time
    output_exe = DIST_DIR / "dns_proxy.exe"
    if output_exe.exists():
        size_mb = output_exe.stat().st_size / (1024 * 1024)
        log(f"Đóng gói thành công: {output_exe.name} ({size_mb:.2f} MB) trong {elapsed:.1f}s", "SUCCESS")
    else:
        raise FileNotFoundError(f"Không tìm thấy file đích sau khi build: {output_exe}")


def build_server(force: bool = False):
    """Biên dịch server/run_server.py thành ogk_server.exe kèm Web Dashboard."""
    log("=" * 70)
    log("3/4. ĐANG ĐÓNG GÓI OGK SERVER & WEB DASHBOARD (ogk_server.exe)...")
    log("=" * 70)

    src_file = BASE_DIR / "server" / "run_server.py"
    if not src_file.exists():
        raise FileNotFoundError(f"Không tìm thấy file nguồn: {src_file}")

    server_files = list((BASE_DIR / "server").rglob("*.py")) + list((BASE_DIR / "server" / "templates").rglob("*.*"))
    latest_src_mtime = max(f.stat().st_mtime for f in server_files) if server_files else src_file.stat().st_mtime
    output_exe = DIST_DIR / "ogk_server.exe"
    if not force and output_exe.exists() and output_exe.stat().st_mtime > latest_src_mtime:
        size_mb = output_exe.stat().st_size / (1024 * 1024)
        log(f"Tái sử dụng bản build hiện có: {output_exe.name} ({size_mb:.2f} MB)", "SUCCESS")
        return

    cmd = [
        "pyinstaller",
        "--clean",
        "--noconfirm",
        "--onefile",
        "--name", "ogk_server",
        "--paths", str(BASE_DIR / "server"),
        "--add-data", f"{BASE_DIR / 'server' / 'templates'};templates",
        "--add-data", f"{BASE_DIR / 'server' / 'static'};static",
        "--hidden-import=uvicorn.logging",
        "--hidden-import=uvicorn.loops",
        "--hidden-import=uvicorn.loops.auto",
        "--hidden-import=uvicorn.protocols",
        "--hidden-import=uvicorn.protocols.http",
        "--hidden-import=uvicorn.protocols.http.auto",
        "--hidden-import=uvicorn.protocols.websockets",
        "--hidden-import=uvicorn.protocols.websockets.auto",
        "--hidden-import=uvicorn.lifespan",
        "--hidden-import=uvicorn.lifespan.on",
        str(src_file),
    ]

    log(f"Thực thi lệnh: {' '.join(cmd)}")
    start_time = time.time()
    result = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        log(f"Lỗi khi build ogk_server.exe:\n{result.stderr}", "ERROR")
        raise RuntimeError("Build ogk_server.exe thất bại!")

    elapsed = time.time() - start_time
    if output_exe.exists():
        size_mb = output_exe.stat().st_size / (1024 * 1024)
        log(f"Đóng gói thành công: {output_exe.name} ({size_mb:.2f} MB) trong {elapsed:.1f}s", "SUCCESS")
    else:
        raise FileNotFoundError(f"Không tìm thấy file đích sau khi build: {output_exe}")


def build_child_client(force: bool = False):
    """(DEPRECATED) Đã chuyển 100% sang Child Web Portal (http://127.0.0.1:8000/child)."""
    log("Bỏ qua đóng gói client native (Đã chuyển toàn diện sang Child Web Portal)", "INFO")
    return


def safe_copy_file(src: Path, dst: Path):
    """Sao chép file an toàn, hỗ trợ hot-swap trên Windows nếu file đang bị tiến trình khóa."""
    try:
        shutil.copy2(src, dst)
    except PermissionError:
        temp_old = dst.with_name(dst.stem + "_old" + dst.suffix)
        if temp_old.exists():
            try:
                temp_old.unlink()
            except Exception:
                pass
        try:
            os.rename(dst, temp_old)
            shutil.copy2(src, dst)
            log(f"Đã hot-swap ghi đè thành công file đang chạy: {dst.name}", "SUCCESS")
        except Exception as e:
            log(f"Không thể ghi đè {dst.name}: {e}", "WARNING")


def create_distribution_package():
    """Tạo thư mục phát hành dist_package/ và sao chép đầy đủ thành phần."""
    log("=" * 70)
    log("TỰ ĐỘNG XÂY DỰNG GÓI PHÁT HÀNH: dist_package/...")
    log("=" * 70)

    # 1. Đảm bảo thư mục đích tồn tại
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)

    # Dọn dẹp các file rác / db tạm thời nếu có từ lần chạy thử trước
    for junk in PACKAGE_DIR.glob("ogk_system.db*"):
        try:
            junk.unlink()
        except Exception:
            pass

    for old_exe in PACKAGE_DIR.glob("*_old.exe"):
        try:
            old_exe.unlink()
            log(f"Đã dọn dẹp file cũ: {old_exe.name}")
        except Exception:
            pass

    # 2. Sao chép ogk_server.exe & templates
    src_server = DIST_DIR / "ogk_server.exe"
    if src_server.exists():
        dst_server = PACKAGE_DIR / "ogk_server.exe"
        log(f"Sao chép {src_server.name} -> {PACKAGE_DIR.name}/")
        safe_copy_file(src_server, dst_server)

    src_templates = BASE_DIR / "server" / "templates"
    if src_templates.exists():
        dst_templates = PACKAGE_DIR / "templates"
        shutil.copytree(src_templates, dst_templates, dirs_exist_ok=True)
        log(f"Sao chép thư mục templates -> {PACKAGE_DIR.name}/templates/")

    src_static = BASE_DIR / "server" / "static"
    if src_static.exists():
        dst_static = PACKAGE_DIR / "static"
        shutil.copytree(src_static, dst_static, dirs_exist_ok=True)
        log(f"Sao chép thư mục static -> {PACKAGE_DIR.name}/static/")

    # 3. Sao chép agent_service.exe
    src_agent = DIST_DIR / "agent_service.exe"
    dst_agent = PACKAGE_DIR / "agent_service.exe"
    log(f"Sao chép {src_agent.name} -> {PACKAGE_DIR.name}/")
    safe_copy_file(src_agent, dst_agent)

    # 4. Sao chép dns_proxy.exe
    src_proxy = DIST_DIR / "dns_proxy.exe"
    dst_proxy = PACKAGE_DIR / "dns_proxy.exe"
    log(f"Sao chép {src_proxy.name} -> {PACKAGE_DIR.name}/")
    safe_copy_file(src_proxy, dst_proxy)

    # 5. Loại bỏ child_client.exe native cũ (Hệ thống chuyển 100% sang Child Web Portal)
    old_child_exe = PACKAGE_DIR / "child_client.exe"
    if old_child_exe.exists():
        try:
            old_child_exe.unlink()
            log("Đã gỡ bỏ child_client.exe native cũ khỏi gói phát hành.")
        except Exception:
            pass

    # 6. Sao chép blocklist.json
    src_blocklist = BASE_DIR / "dns_proxy" / "blocklist.json"
    dst_blocklist = PACKAGE_DIR / "blocklist.json"
    log(f"Sao chép {src_blocklist.name} -> {PACKAGE_DIR.name}/")
    shutil.copy2(src_blocklist, dst_blocklist)

    # 6. Tạo file Launcher 1-Click: Start_App.bat & Stop_App.bat
    start_app_path = PACKAGE_DIR / "Start_App.bat"
    log(f"Tạo file khởi chạy 1-Click: {start_app_path.name}")
    start_app_path.write_text(START_APP_BAT, encoding="utf-8")

    stop_app_path = PACKAGE_DIR / "Stop_App.bat"
    log(f"Tạo file dừng hệ thống: {stop_app_path.name}")
    stop_app_path.write_text(STOP_APP_BAT, encoding="utf-8")

    # 7. Tạo file install_service.bat, start_proxy.bat, uninstall_service.bat
    install_bat_path = PACKAGE_DIR / "install_service.bat"
    log(f"Tạo file kịch bản cài đặt: {install_bat_path.name}")
    install_bat_path.write_text(INSTALL_SERVICE_BAT, encoding="utf-8")

    proxy_bat_path = PACKAGE_DIR / "start_proxy.bat"
    log(f"Tạo file kịch bản khởi chạy DNS: {proxy_bat_path.name}")
    proxy_bat_path.write_text(START_PROXY_BAT, encoding="utf-8")

    uninstall_bat_path = PACKAGE_DIR / "uninstall_service.bat"
    log(f"Tạo file kịch bản gỡ bỏ: {uninstall_bat_path.name}")
    uninstall_bat_path.write_text(UNINSTALL_SERVICE_BAT, encoding="utf-8")

    # 8. Tạo file HUONG_DAN_CAI_DAT.txt & HUONG_DAN_CHAY_DONG_GOI.md & README_DEPLOY.md
    guide_path = PACKAGE_DIR / "HUONG_DAN_CAI_DAT.txt"
    guide_path.write_text(HUONG_DAN_CAI_DAT_TXT, encoding="utf-8")

    src_guide_md = BASE_DIR / "HUONG_DAN_CHAY_DONG_GOI.md"
    if src_guide_md.exists():
        shutil.copy2(src_guide_md, PACKAGE_DIR / "HUONG_DAN_CHAY_DONG_GOI.md")

    src_readme_deploy = BASE_DIR / "README_DEPLOY.md"
    if src_readme_deploy.exists():
        shutil.copy2(src_readme_deploy, PACKAGE_DIR / "README_DEPLOY.md")

    # 9. Tạo file mã băm SHA256SUMS.txt kiểm tra tính toàn vẹn (DevOps Integrity Standard)
    import hashlib
    checksums = []
    for item in sorted(PACKAGE_DIR.glob("*")):
        if item.is_file() and item.name != "SHA256SUMS.txt" and not item.name.endswith("_old.exe") and not item.name.startswith("ogk_system.db"):
            sha = hashlib.sha256(item.read_bytes()).hexdigest()
            checksums.append(f"{sha}  {item.name}")
    checksum_path = PACKAGE_DIR / "SHA256SUMS.txt"
    checksum_path.write_text("\n".join(checksums) + "\n", encoding="utf-8")
    log("Đã tạo bảng mã băm SHA256SUMS.txt kiểm tra tính toàn vẹn.")

    # 10. Tạo file nén ZIP để phân phối một file tiện lợi
    zip_dst = DIST_DIR / "OGK_Deploy_Package_x64"
    zip_file = shutil.make_archive(str(zip_dst), "zip", root_dir=str(PACKAGE_DIR))
    log(f"Đã nén gói triển khai thành file ZIP: {Path(zip_file).name} ({os.path.getsize(zip_file) / (1024 * 1024):.2f} MB)", "SUCCESS")

    # Tổng kết danh sách file trong dist_package
    log("=" * 70)
    log("DANH SÁCH THÀNH PHẦN HOÀN CHỈNH TRONG dist_package/:", "SUCCESS")
    total_size = 0
    for p in sorted(PACKAGE_DIR.glob("*")):
        sz = p.stat().st_size
        total_size += sz
        if sz >= 1024 * 1024:
            sz_str = f"{sz / (1024 * 1024):6.2f} MB"
        else:
            sz_str = f"{sz / 1024:6.2f} KB"
        print(f"  ├── {p.name:<25} ({sz_str})")
    log(f"Tổng dung lượng gói triển khai: {total_size / (1024 * 1024):.2f} MB", "SUCCESS")
    log(f"Đường dẫn thư mục phát hành: {PACKAGE_DIR.resolve()}", "SUCCESS")
    log("Gói này có thể copy trực tiếp sang bất kỳ máy tính Windows 10/11 x64 nào để chạy!", "SUCCESS")


def main():
    start_total = time.time()
    print("*" * 70)
    print("   OGK SYSTEM - QUY TRÌNH ĐÓNG GÓI VÀ TẠO BỘ TRIỂN KHAI PHÁT HÀNH")
    print("*" * 70)

    force = "--force" in sys.argv or "-f" in sys.argv

    try:
        check_and_install_dependencies()
        build_agent_service(force=force)
        build_dns_proxy(force=force)
        build_server(force=force)
        create_distribution_package()
        total_elapsed = time.time() - start_total
        print("*" * 70)
        log(f"QUY TRÌNH ĐÓNG GÓI HOÀN TẤT THÀNH CÔNG TRONG {total_elapsed:.1f} GIÂY!", "SUCCESS")
        print("*" * 70)
    except Exception as exc:
        log(f"QUY TRÌNH ĐÓNG GÓI THẤT BẠI: {exc}", "ERROR")
        sys.exit(1)


if __name__ == "__main__":
    main()

