@echo off
setlocal
cd /d "%~dp0"

title OGK Launcher
echo ========================================
echo   OGK - Khoi dong Server va mo Web
echo ========================================

if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv .venv
    ) else (
        where python >nul 2>nul
        if errorlevel 1 (
            echo Khong tim thay Python 3. Hay cai Python 3.11+ va chon Add Python to PATH.
            pause
            exit /b 1
        )
        python -m venv .venv
    )
    if errorlevel 1 goto :venv_failed
)

set "PYTHON=%~dp0.venv\Scripts\python.exe"
"%PYTHON%" -c "import fastapi, uvicorn, sqlalchemy, jose, jinja2, multipart, argon2, psutil, requests, websockets" >nul 2>nul
if errorlevel 1 (
    echo Dang cai dat cac thu vien can thiet...
    "%PYTHON%" -m pip install -r "%~dp0requirements.txt"
    if errorlevel 1 goto :install_failed
)

"%PYTHON%" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=1)" >nul 2>nul
if errorlevel 1 (
    echo Dang khoi dong server...
    start "OGK Server" /D "%~dp0" "%PYTHON%" "%~dp0run_server.py"
    call :wait_for_server
    if errorlevel 1 goto :server_failed
) else (
    echo Server da chay san.
)

start "" "http://127.0.0.1:8000/"
start "" "http://127.0.0.1:8000/child"
echo Da mo Dashboard va trang Child tren trinh duyet.
echo Dong cua so OGK Server de dung server.
exit /b 0

:wait_for_server
for /L %%I in (1,1,45) do (
    "%PYTHON%" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=1)" >nul 2>nul
    if not errorlevel 1 exit /b 0
    timeout /t 1 /nobreak >nul
)
exit /b 1

:venv_failed
echo Khong tao duoc moi truong Python.
pause
exit /b 1

:install_failed
echo Cai dat thu vien that bai. Hay kiem tra ket noi Internet.
pause
exit /b 1

:server_failed
echo Server khong khoi dong duoc. Kiem tra cua so OGK Server va thu lai.
pause
exit /b 1
