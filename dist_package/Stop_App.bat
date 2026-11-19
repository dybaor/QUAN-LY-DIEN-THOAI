@echo off
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
