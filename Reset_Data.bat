@echo off
chcp 65001 >nul
title [OGK] Reset Du Lieu He Thong (Clean State)
echo ==============================================================================
echo [OGK] DANG RESET DU LIEU VE TRANG THAI KHOI TAO BAN DAU (TRUONG HOP A)...
echo ==============================================================================

python reset_database.py

echo.
echo Da hoan tat reset! Hay tai lai trang web Phuhuynh (http://127.0.0.1:8000)
echo de trai nghiem man hinh Thiet lap Ho so Ban dau.
echo ==============================================================================
pause

