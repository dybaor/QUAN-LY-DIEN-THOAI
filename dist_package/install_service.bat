@echo off
chcp 65001 >nul
title [OGK-AGENT] Cai Dat Windows Service

echo ==============================================================================
echo [OGK-AGENT] KHOI TAO CAI DAT WINDOWS SERVICE: OGKChildAgent (LocalSystem)
echo ==============================================================================

:: 1. Kiem tra quyen Administrator
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] BAN PHAI CHAY FILE NAY VOI QUYEN "RUN AS ADMINISTRATOR"!
    echo         Click chuot phai vao file install_service.bat -^> chon "Run as administrator".
    echo ==============================================================================
    pause
    exit /b 1
)

:: 2. Kiem tra file thuc thi agent_service.exe
if not exist "%~dp0agent_service.exe" (
    echo [ERROR] Khong tim thay file "agent_service.exe" trong thu muc hien tai!
    echo         Vui long kiem tra lai bo cai dat.
    echo ==============================================================================
    pause
    exit /b 1
)

:: 3. Tao thu muc luu tru du lieu %ProgramData%\OGKAgent va phan quyen
set AGENT_DATA=%ProgramData%\OGKAgent
if not exist "%AGENT_DATA%" (
    mkdir "%AGENT_DATA%"
)
if not exist "%AGENT_DATA%\logs" (
    mkdir "%AGENT_DATA%\logs"
)
icacls "%AGENT_DATA%" /inheritance:r /grant:r "NT AUTHORITY\SYSTEM":(OI)(CI)F /grant:r "BUILTIN\Administrators":(OI)(CI)F >nul 2>&1

:: 4. Dung va xoa phien ban cu cua dich vu neu dang ton tai
echo [INFO] Kiem tra va go bo phien ban cu neu co...
net stop OGKChildAgent >nul 2>&1
sc stop OGKChildAgent >nul 2>&1
sc delete OGKChildAgent >nul 2>&1
timeout /t 2 /nobreak >nul

:: 5. Dang ky dich vu Windows moi chay duoi quyen LocalSystem
echo [INFO] Dang dang ky dich vu Windows: OGKChildAgent...
sc create "OGKChildAgent" binPath= "\"%~dp0agent_service.exe\"" start= auto DisplayName= "OGK Child Monitoring Agent" obj= LocalSystem
if %errorlevel% neq 0 (
    echo [ERROR] Dang ky dich vu that bai!
    pause
    exit /b 1
)

:: 6. Dat mo ta cho dich vu
sc description "OGKChildAgent" "He thong quan ly thoi gian su dung thiet bi cho tre em (Do an Nguoi Ban Dong Hanh). Theo doi tien trinh, dem gio, chan ung dung va dong bo chinh sach." >nul 2>&1

:: 7. Cau hinh co che tu dong khoi phuc khi crash sau 5 giay (Tieu chuan Chuyen de M5)
echo [INFO] Cau hinh Recovery Options (Tu dong Restart sau 5 giay khi Service gap su co)...
sc failure "OGKChildAgent" reset= 86400 actions= restart/5000/restart/5000/restart/5000

:: 8. Khoi chay dich vu
echo [INFO] Dang khoi dong dich vu OGKChildAgent...
sc start OGKChildAgent
timeout /t 2 /nobreak >nul

:: 9. Kiem tra trang thai va bao cao ket qua
echo.
echo ==============================================================================
echo [THONG TIN CAU HINH PHUC HOI M5]
sc qfailure OGKChildAgent
echo ==============================================================================
echo [TRANG THAI HOAT DONG DICH VU]
sc query OGKChildAgent
echo ==============================================================================
echo [SUCCESS] DICH VU OGKChildAgent DA DUOC CAI DAT VA KHOI DONG THANH CONG!
echo           Dich vu se tu dong khoi dong cung Windows va chay ngam LocalSystem.
echo ==============================================================================
pause
