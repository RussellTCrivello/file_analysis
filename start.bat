@echo off
REM =====================================================================
REM  File Analysis - Windows one-click start
REM  Double-click this file every time you want to use the application.
REM =====================================================================
title File Analysis - Server
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo  [ERROR] The application is not set up yet.
    echo  Please double-click  setup.bat  first (one time only).
    echo.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

echo.
echo  ============================================================
echo   Starting File Analysis...
echo   Open your browser at:  http://127.0.0.1:5000
echo   Press CTRL+C to stop the server.
echo  ============================================================
echo.

python run_web.py

echo.
echo  The server has stopped. If you saw an error above, check
echo  the "Troubleshooting" section in INSTALL.md.
echo.
pause
