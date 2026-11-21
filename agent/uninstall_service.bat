@echo off
:: OGK-Agent (ma nguon): go cai dat hop phap - bat buoc tai khoan phu huynh,
:: co ghi log cuc bo va audit log tren may chu.
net session >nul 2>&1
if errorlevel 1 (
    echo [LOI] Chuot phai vao file nay va chon "Run as administrator".
    pause
    exit /b 1
)
python "%~dp0uninstall_agent.py"
pause
