@echo off
setlocal enabledelayedexpansion
title JS AudioRouter - Setup and Launch
color 0B

echo ============================================
echo   JS AudioRouter - Environment Check
echo ============================================
echo.

REM --- 1. Check Python ---
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [X] Python not found in PATH.
    echo     Install Python 3.11 from https://www.python.org/downloads/
    echo     Make sure "Add Python to PATH" is checked during install.
    pause
    exit /b 1
) else (
    for /f "tokens=2" %%v in ('python --version') do set PYVER=%%v
    echo [OK] Python !PYVER! found
)

REM --- 2. Check / create virtual environment ---
if not exist "venv\" (
    echo [..] Creating virtual environment...
    python -m venv venv
) else (
    echo [OK] Virtual environment already exists
)

call venv\Scripts\activate.bat

REM --- 3. Install / verify dependencies ---
echo [..] Checking dependencies...
pip install -q -r requirements.txt
if %errorlevel% neq 0 (
    echo [X] Dependency install failed. Check your internet connection.
    pause
    exit /b 1
) else (
    echo [OK] Dependencies installed
)

REM --- 4. Check for VB-Audio Cable via registry ---
echo [..] Checking for VB-Audio Virtual Cable...
reg query "HKLM\SOFTWARE\VB-Audio" >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Could not confirm VB-Audio Cable via registry.
    echo     The app will still double-check via device list at launch.
    echo     If not installed, get it free from: https://vb-audio.com/Cable/
) else (
    echo [OK] VB-Audio Cable registry entry found
)

REM --- 5. List available audio devices for a sanity check ---
echo.
echo ============================================
echo   Detected Audio Output Devices
echo ============================================
python core\device_manager.py
echo.

REM --- 6. Launch the app ---
echo ============================================
echo   Launching JS AudioRouter...
echo ============================================
python gui\main.py

pause
