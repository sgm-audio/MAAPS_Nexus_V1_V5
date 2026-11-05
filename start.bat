@echo off
title MAAPS Nexus
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
    echo Python is not installed or not on PATH.
    echo Install it from https://www.python.org/downloads/ - check "Add to PATH".
    pause
    exit /b 1
)
python run.py %*
echo.
pause
