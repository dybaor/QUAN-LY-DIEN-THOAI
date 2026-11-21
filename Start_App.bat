@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title OGK Launcher

::  ============================================================================
::  OGK - Nguoi Ban Dong Hanh: launcher duy nhat cho Windows
::  Chay tu ma nguon (tu tao .venv) hoac tu goi da build (ogk_server.exe nam canh file nay).
::
::    Start_App.bat                 Bat may chu, mo Dashboard + Cong hoc tap
::    Start_App.bat --server-only   Chi bat may chu (dung voi OGKParent.exe / OGKChild.exe)
::    Start_App.bat --with-agent    Bat them Agent che do debug (may da ghep doi)
::    Start_App.bat --with-dns      Bat them DNS Proxy (can Run as administrator)
::    Start_App.bat --reset         Xoa du lieu, dua he thong ve trang thai chua co tai khoan
::    Start_App.bat --stop          Dung may chu, Agent debug va DNS Proxy
::  ============================================================================

set "OPEN_BROWSER=1"
set "WITH_AGENT=0"
set "WITH_DNS=0"
set "RESET=0"
:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="--server-only" set "OPEN_BROWSER=0"
if /i "%~1"=="--with-agent" set "WITH_AGENT=1"
if /i "%~1"=="--with-dns" set "WITH_DNS=1"
if /i "%~1"=="--reset" set "RESET=1"
if /i "%~1"=="--stop" goto stop
if /i "%~1"=="--help" goto help
shift
goto parse_args
:args_done

set "URL=http://127.0.0.1:8000"
set "PACKAGED=0"
if exist "%~dp0ogk_server.exe" set "PACKAGED=1"

if "%PACKAGED%"=="0" (
    call :prepare_python
    if errorlevel 1 exit /b 1
)

call :check_server
if errorlevel 1 goto start_server
if "%RESET%"=="1" (
    echo [LOI] May chu dang chay. Chay "Start_App.bat --stop" truoc khi reset du lieu.
    pause
    exit /b 1
)
echo May chu OGK da chay san.
goto server_ready

:start_server
if "%RESET%"=="1" (
    call :reset_data
    if errorlevel 1 exit /b 1
)
echo Dang khoi dong may chu OGK...
if "%PACKAGED%"=="1" start "OGK Server" /D "%~dp0" "%~dp0ogk_server.exe"
if "%PACKAGED%"=="0" start "OGK Server" /D "%~dp0" "%PYTHON%" "%~dp0server\run_server.py"
call :wait_for_server
if errorlevel 1 goto server_failed

:server_ready
if "%WITH_AGENT%"=="1" call :start_agent
if "%WITH_DNS%"=="1" call :start_dns
if "%OPEN_BROWSER%"=="0" goto done
start "" "%URL%/"
start "" "%URL%/child"
echo Da mo Dashboard phu huynh va Cong hoc tap tren trinh duyet.
:done
echo May chu chay trong cua so "OGK Server". Dong cua so do hoac chay "Start_App.bat --stop" de dung.
exit /b 0

:: ----------------------------------------------------------------------------
:prepare_python
if exist "%~dp0.venv\Scripts\python.exe" goto venv_ready
echo Dang tao moi truong Python .venv...
where py >nul 2>nul
if not errorlevel 1 py -3 -m venv "%~dp0.venv"
if exist "%~dp0.venv\Scripts\python.exe" goto venv_ready
where python >nul 2>nul
if errorlevel 1 goto no_python
python -m venv "%~dp0.venv"
if not exist "%~dp0.venv\Scripts\python.exe" goto no_python
:venv_ready
set "PYTHON=%~dp0.venv\Scripts\python.exe"
"%PYTHON%" -c "import fastapi, uvicorn, sqlalchemy, jose, jinja2, argon2, cryptography, websockets" >nul 2>nul
if errorlevel 1 (
    echo Dang cai thu vien may chu...
    "%PYTHON%" -m pip install --disable-pip-version-check -q -r "%~dp0server\requirements.txt"
    if errorlevel 1 goto install_failed
)
if "%WITH_AGENT%"=="1" (
    "%PYTHON%" -m pip install --disable-pip-version-check -q -r "%~dp0agent\requirements.txt"
    if errorlevel 1 goto install_failed
)
if "%WITH_DNS%"=="1" (
    "%PYTHON%" -m pip install --disable-pip-version-check -q dnslib
    if errorlevel 1 goto install_failed
)
exit /b 0

:check_server
curl -fs --max-time 1 "%URL%/health" 2>nul | find "OGK-Server" >nul
exit /b %errorlevel%

:wait_for_server
for /L %%I in (1,1,45) do (
    call :check_server && exit /b 0
    ping -n 2 127.0.0.1 >nul
)
exit /b 1

:reset_data
echo Dang dua du lieu ve trang thai ban dau...
if "%PACKAGED%"=="1" (
    del /q "%~dp0ogk_system.db" "%~dp0ogk_system.db-wal" "%~dp0ogk_system.db-shm" 2>nul
    exit /b 0
)
"%PYTHON%" "%~dp0reset_database.py"
exit /b %errorlevel%

:start_agent
echo Dang bat Agent debug kem bieu tuong khay he thong...
if exist "%~dp0agent_service.exe" (
    start "OGK Agent" /D "%~dp0" "%~dp0agent_service.exe" debug
) else (
    start "OGK Agent" /D "%~dp0agent" "%PYTHON%" "%~dp0agent\main_service.py" debug
)
exit /b 0

:start_dns
net session >nul 2>&1
if errorlevel 1 (
    echo [CANH BAO] DNS Proxy can cong UDP 53: hay chay launcher bang "Run as administrator". Bo qua DNS Proxy.
    exit /b 0
)
echo Dang bat DNS Proxy tai 127.0.0.1:53...
if exist "%~dp0dns_proxy.exe" (
    start "OGK DNS Proxy" /D "%~dp0" "%~dp0dns_proxy.exe"
) else (
    start "OGK DNS Proxy" /D "%~dp0dns_proxy" "%PYTHON%" "%~dp0dns_proxy\proxy_server.py"
)
exit /b 0

:stop
echo Dang dung cac tien trinh OGK...
for %%T in ("OGK Server" "OGK Agent" "OGK DNS Proxy") do taskkill /FI "WINDOWTITLE eq %%~T*" /T /F >nul 2>&1
for %%E in (ogk_server.exe agent_service.exe dns_proxy.exe) do taskkill /IM %%E /T /F >nul 2>&1
echo Da dung.
exit /b 0

:help
findstr /b /c:"::    " "%~f0"
exit /b 0

:no_python
echo [LOI] Khong tim thay Python 3.11+. Cai Python va chon "Add Python to PATH".
pause
exit /b 1

:install_failed
echo [LOI] Cai thu vien that bai. Kiem tra ket noi Internet roi thu lai.
pause
exit /b 1

:server_failed
echo [LOI] May chu khong khoi dong duoc. Xem thong bao trong cua so "OGK Server".
pause
exit /b 1
