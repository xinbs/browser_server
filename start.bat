@echo off
chcp 65001
cls

set ROOT=%~dp0
cd /d %ROOT%

if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate
) else (
    echo Virtual environment not found
    pause
    exit /b 1
)

set BROWSER_HOST=0.0.0.0
set BROWSER_PORT=3456
set BROWSER_USER_DATA_DIR=%ROOT%user_data
set BROWSER_HEADLESS=false

python browser_server.py

pause
