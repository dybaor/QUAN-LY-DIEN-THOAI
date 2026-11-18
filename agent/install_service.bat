@echo off
chcp 65001 >nul
:: ==============================================================================
:: OGK-Agent Service Installer Script (Thành viên A)
:: Tạo Windows Service "OGKChildAgent" quyền LocalSystem + Tự restart sau 5s
:: Yêu cầu quyền Quản trị viên (Run as Administrator)
:: ==============================================================================

echo ==============================================================================
echo [OGK-AGENT] KHỞI TẠO CÀI ĐẶT WINDOWS SERVICE: OGKChildAgent (LocalSystem)
echo ==============================================================================

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] BẠN PHẢI CHẠY FILE NÀY VỚI QUYỀN "RUN AS ADMINISTRATOR"!
    pause
    exit /b 1
)

set AGENT_DATA=%ProgramData%\OGKAgent
if not exist "%AGENT_DATA%" (
    mkdir "%AGENT_DATA%"
    mkdir "%AGENT_DATA%\logs"
)
icacls "%AGENT_DATA%" /inheritance:r /grant:r "NT AUTHORITY\SYSTEM":(OI)(CI)F /grant:r "BUILTIN\Administrators":(OI)(CI)F >nul

echo [INFO] Đang đăng ký dịch vụ OGKChildAgent...
python "%~dp0main_service.py" install --startup auto

echo [INFO] Cấu hình Recovery Options (Restart sau 5 giây khi crash)...
sc failure OGKChildAgent reset= 86400 actions= restart/5000/restart/5000/restart/5000
sc config OGKChildAgent start= auto obj= "LocalSystem"

echo [INFO] Khởi động dịch vụ OGKChildAgent...
net start OGKChildAgent

echo.
sc qfailure OGKChildAgent
sc query OGKChildAgent

echo ==============================================================================
echo [SUCCESS] CÀI ĐẶT HOÀN TẤT DỊCH VỤ OGKChildAgent!
echo ==============================================================================
pause

