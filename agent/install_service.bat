@echo off
setlocal EnableExtensions
:: ============================================================================
:: OGK-Agent (ma nguon): ghep doi may, cai Windows Service "OGKChildAgent"
:: (LocalSystem, tu khoi dong lai sau 5s) va dang ky bieu tuong khay he thong
:: chay khi nguoi dung dang nhap. Yeu cau Run as Administrator.
:: ============================================================================
net session >nul 2>&1
if errorlevel 1 (
    echo [LOI] Chuot phai vao file nay va chon "Run as administrator".
    pause
    exit /b 1
)

set "AGENT_DIR=%~dp0"
set "AGENT_DATA=%ProgramData%\OGKAgent"
if not exist "%AGENT_DATA%\logs" mkdir "%AGENT_DATA%\logs"
icacls "%AGENT_DATA%" /inheritance:r /grant:r "NT AUTHORITY\SYSTEM":(OI)(CI)F /grant:r "BUILTIN\Administrators":(OI)(CI)F >nul

where pythonw >nul 2>nul
if errorlevel 1 (
    echo [LOI] Khong tim thay Python. Cai Python 3.11+ va chon "Add Python to PATH".
    pause
    exit /b 1
)
python -m pip install --quiet -r "%AGENT_DIR%requirements.txt"
if errorlevel 1 goto failed

echo.
echo Mo Dashboard phu huynh ^> "Thiet bi cua tre" ^> "Tao ma ghep doi" de lay ma 8 ky tu (han 10 phut).
set /p "PAIR_CODE=Nhap ma ghep doi: "
python "%AGENT_DIR%main_service.py" enroll %PAIR_CODE%
if errorlevel 1 goto failed

python "%AGENT_DIR%main_service.py" --startup auto install
if errorlevel 1 goto failed
sc failure OGKChildAgent reset= 86400 actions= restart/5000/restart/5000/restart/5000 >nul
sc config OGKChildAgent start= auto obj= "LocalSystem" >nul

:: Bieu tuong khay bat buoc chay trong phien cua tre (Agent tu dung giam sat neu thieu).
for /f "delims=" %%P in ('where pythonw') do if not defined PYW set "PYW=%%P"
reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Run" /v OGKTray /t REG_SZ /d "\"%PYW%\" \"%AGENT_DIR%tray_ui.py\"" /f >nul
start "" "%PYW%" "%AGENT_DIR%tray_ui.py"

net start OGKChildAgent
sc query OGKChildAgent | find "STATE"
echo [OK] Da cai OGK Agent. Bieu tuong OGK xuat hien o khay he thong.
pause
exit /b 0

:failed
echo [LOI] Cai dat that bai. Xem thong bao phia tren.
pause
exit /b 1
