@echo off
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
