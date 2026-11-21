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

for _stream in (sys.stdout, sys.stderr):  # In tiếng Việt được cả khi ghi log ra file / CI
    if _stream and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")
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
title [OGK-AGENT] Cai Dat Agent
:: Ghep doi may, cai Windows Service OGKChildAgent (LocalSystem, tu khoi dong lai sau 5s)
:: va dang ky bieu tuong khay he thong chay khi nguoi dung dang nhap.
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Chuot phai vao file nay va chon "Run as administrator".
    pause
    exit /b 1
)
if not exist "%~dp0agent_service.exe" (
    echo [ERROR] Khong tim thay agent_service.exe trong thu muc hien tai.
    pause
    exit /b 1
)
set "AGENT_DATA=%ProgramData%\OGKAgent"
if not exist "%AGENT_DATA%\logs" mkdir "%AGENT_DATA%\logs"
icacls "%AGENT_DATA%" /inheritance:r /grant:r "NT AUTHORITY\SYSTEM":(OI)(CI)F /grant:r "BUILTIN\Administrators":(OI)(CI)F >nul 2>&1

echo Mo Dashboard phu huynh ^> "Thiet bi cua tre" ^> "Tao ma ghep doi" (han 10 phut).
set /p "PAIR_CODE=Nhap ma ghep doi 8 ky tu: "
"%~dp0agent_service.exe" enroll %PAIR_CODE%
if %errorlevel% neq 0 (
    echo [ERROR] Ghep doi that bai. Kiem tra ma va ket noi toi may chu OGK.
    pause
    exit /b 1
)

sc stop OGKChildAgent >nul 2>&1
sc delete OGKChildAgent >nul 2>&1
timeout /t 2 /nobreak >nul
sc create "OGKChildAgent" binPath= "\"%~dp0agent_service.exe\"" start= auto DisplayName= "OGK Child Monitoring Agent" obj= LocalSystem
if %errorlevel% neq 0 (
    echo [ERROR] Dang ky dich vu that bai!
    pause
    exit /b 1
)
sc description "OGKChildAgent" "Quan ly thoi gian su dung va bao ve thiet bi cho tre em (luon hien bieu tuong khay)." >nul 2>&1
sc failure "OGKChildAgent" reset= 86400 actions= restart/5000/restart/5000/restart/5000 >nul

reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Run" /v OGKTray /t REG_SZ /d "\"%~dp0ogk_tray.exe\"" /f >nul
start "" "%~dp0ogk_tray.exe"
sc start OGKChildAgent
timeout /t 2 /nobreak >nul
sc query OGKChildAgent | find "STATE"
echo [SUCCESS] Da cai OGK Agent. Bieu tuong OGK xuat hien o khay he thong.
pause
"""

UNINSTALL_SERVICE_BAT = r"""@echo off
title [OGK-AGENT] Go Cai Dat Agent
:: Go cai dat hop phap: bat buoc tai khoan phu huynh, co ghi log cuc bo va audit log tren may chu.
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Chuot phai vao file nay va chon "Run as administrator".
    pause
    exit /b 1
)
"%~dp0agent_service.exe" uninstall
pause
"""

HUONG_DAN_CAI_DAT_TXT = """================================================================================
HƯỚNG DẪN TRIỂN KHAI VÀ SỬ DỤNG GÓI PHÁT HÀNH (DIST_PACKAGE)
Dự án: "Người Bạn Đồng Hành" (OGK Child Device & Network Protection System)
Thời gian triển khai: Dưới 5 phút | Không yêu cầu cài đặt Python
================================================================================

I. CẤU TRÚC GÓI PHÁT HÀNH (dist_package)
--------------------------------------------------------------------------------
├── Start_App.bat          : Launcher duy nhất (máy chủ, --with-agent, --with-dns, --reset, --stop)
├── ogk_server.exe         : Máy chủ OGK + Dashboard phụ huynh + Cổng học tập của trẻ
├── agent_service.exe      : Agent (Windows Service, lệnh enroll / debug / uninstall)
├── ogk_tray.exe           : Biểu tượng khay hệ thống bắt buộc trong phiên của trẻ
├── dns_proxy.exe          : Máy chủ DNS Proxy lọc 6 nhóm nội dung, SafeSearch, chặn DoH
├── blocklist.json         : Danh mục tên miền theo 6 nhóm nội dung
├── install_service.bat    : Ghép đôi + cài Windows Service + đăng ký khay hệ thống
├── uninstall_service.bat  : Gỡ cài đặt (bắt buộc tài khoản phụ huynh)
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
   Bước 1: Mở Command Prompt bằng "Run as administrator" trong thư mục gói.
   Bước 2: Chạy `Start_App.bat --with-dns --server-only` (hoặc bỏ --server-only nếu máy chủ chạy trên máy này).
   Bước 3: Cửa sổ "OGK DNS Proxy" hiện thông báo đang lắng nghe tại UDP 127.0.0.1:53.
   Bước 4: Đổi DNS của Card mạng (Network Adapter) trên máy tính con:
           + Mở Control Panel -> Network and Sharing Center -> Change adapter settings.
           + Click chuột phải vào Wi-Fi hoặc Ethernet -> Properties.
           + Chọn "Internet Protocol Version 4 (TCP/IPv4)" -> Properties.
           + Chọn "Use the following DNS server addresses":
             Preferred DNS server: 127.0.0.1
             (Không đặt DNS thay thế, nếu không trình duyệt có thể vượt bộ lọc)
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
- Click chuột phải vào file `uninstall_service.bat` -> Chọn "Run as administrator".
  Nhập tên đăng nhập và mật khẩu phụ huynh. Máy chủ ghi audit log, sau đó dịch vụ
  `OGKChildAgent`, biểu tượng khay và bộ nhớ đệm được gỡ khỏi máy.

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
        sys.executable, "-m", "PyInstaller",  # đúng interpreter đã cài thư viện (không dùng pyinstaller tìm theo PATH)
        "--clean",
        "--noconfirm",
        "--onefile",
        "--name", "agent_service",
        "--paths", str(BASE_DIR / "agent"),
        "--hidden-import=win32timezone",
        "--hidden-import=win32serviceutil",
        "--hidden-import=win32service",
        "--hidden-import=win32event",
        "--hidden-import=psutil",
        "--hidden-import=win32crypt",
        "--hidden-import=servicemanager",
        "--hidden-import=win32pipe",
        "--hidden-import=win32security",
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


def build_tray(force: bool = False):
    """Biên dịch agent/tray_ui.py thành ogk_tray.exe (không console) chạy trong phiên của trẻ."""
    log("=" * 70)
    log("1b/4. ĐANG ĐÓNG GÓI BIỂU TƯỢNG KHAY HỆ THỐNG (ogk_tray.exe)...")
    log("=" * 70)
    src_file = BASE_DIR / "agent" / "tray_ui.py"
    output_exe = DIST_DIR / "ogk_tray.exe"
    latest_src_mtime = max(f.stat().st_mtime for f in (BASE_DIR / "agent").glob("*.py"))
    if not force and output_exe.exists() and output_exe.stat().st_mtime > latest_src_mtime:
        log(f"Tái sử dụng bản build hiện có: {output_exe.name}", "SUCCESS")
        return
    cmd = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "--onefile", "--noconsole", "--name", "ogk_tray",
           "--paths", str(BASE_DIR / "agent"), "--hidden-import=win32pipe", str(src_file)]
    log(f"Thực thi lệnh: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0 or not output_exe.exists():
        log(f"Lỗi khi build ogk_tray.exe:\n{result.stderr}", "ERROR")
        raise RuntimeError("Build ogk_tray.exe thất bại!")
    log(f"Đóng gói thành công: {output_exe.name}", "SUCCESS")


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
        sys.executable, "-m", "PyInstaller",  # đúng interpreter đã cài thư viện (không dùng pyinstaller tìm theo PATH)
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
        sys.executable, "-m", "PyInstaller",  # đúng interpreter đã cài thư viện (không dùng pyinstaller tìm theo PATH)
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
        "--hidden-import=uvicorn.protocols.websockets.websockets_sansio_impl",
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

    src_tray = DIST_DIR / "ogk_tray.exe"
    log(f"Sao chép {src_tray.name} -> {PACKAGE_DIR.name}/")
    safe_copy_file(src_tray, PACKAGE_DIR / "ogk_tray.exe")

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

    # 7. Launcher duy nhất (dùng chung với bản mã nguồn) và kịch bản cài / gỡ Agent
    log("Sao chép launcher Start_App.bat")
    shutil.copy2(BASE_DIR / "Start_App.bat", PACKAGE_DIR / "Start_App.bat")
    for legacy in ("Stop_App.bat", "start_proxy.bat"):
        (PACKAGE_DIR / legacy).unlink(missing_ok=True)
    # File .bat phải là ASCII + CRLF thì cmd.exe mới phân tích đúng nhãn và lệnh
    (PACKAGE_DIR / "install_service.bat").write_text(INSTALL_SERVICE_BAT, encoding="ascii", newline="\r\n")
    (PACKAGE_DIR / "uninstall_service.bat").write_text(UNINSTALL_SERVICE_BAT, encoding="ascii", newline="\r\n")

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
        build_tray(force=force)
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

