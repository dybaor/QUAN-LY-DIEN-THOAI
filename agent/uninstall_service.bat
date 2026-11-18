@echo off
chcp 65001 >nul
:: ==============================================================================
:: OGK-Agent Service Uninstaller Script (Thành viên A)
:: ==============================================================================

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] BẠN PHẢI CHẠY FILE NÀY VỚI QUYỀN "RUN AS ADMINISTRATOR"!
    pause
    exit /b 1
)

echo [INFO] Dừng dịch vụ OGKChildAgent...
net stop OGKChildAgent >nul 2>&1

echo [INFO] Gỡ bỏ dịch vụ...
python "%~dp0main_service.py" remove >nul 2>&1
sc delete OGKChildAgent >nul 2>&1

echo [SUCCESS] Đã gỡ bỏ dịch vụ OGKChildAgent thành công!
pause

