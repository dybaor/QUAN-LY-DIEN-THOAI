@echo off
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
