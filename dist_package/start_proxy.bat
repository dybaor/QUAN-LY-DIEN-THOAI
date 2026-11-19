@echo off
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
