@echo off
setlocal enabledelayedexpansion
title GitForge Studio
cd /d "%~dp0"

echo ============================================
echo   GitForge Studio - Startup Check
echo ============================================
echo.

REM ---- Check Python ----
where python >nul 2>nul
if errorlevel 1 (
    echo [X] Python not found.
    echo     Install Python 3.8+ from https://www.python.org/downloads/
    echo     During install, check "Add python.exe to PATH".
    pause
    exit /b 1
) else (
    echo [OK] Python found:
    python --version
)

echo.

REM ---- Check Git ----
where git >nul 2>nul
if errorlevel 1 (
    echo [X] Git not found.
    echo     GitForge Studio is a cockpit for Git - it needs the real Git engine.
    echo     Install "Git for Windows" from https://git-scm.com/downloads
    pause
    exit /b 1
) else (
    echo [OK] Git found:
    git --version
)

echo.

REM ---- Soft check: global identity ----
for /f "delims=" %%i in ('git config --global user.name 2^>nul') do set GIT_NAME=%%i
if "%GIT_NAME%"=="" (
    echo [!] Git global user.name is not set yet.
    echo     GitForge Studio's Git Doctor can help you fix this on first launch.
) else (
    echo [OK] Git identity: %GIT_NAME%
)

echo.

REM ---- Optional: GitHub CLI ----
where gh >nul 2>nul
if errorlevel 1 (
    echo [i] GitHub CLI (gh) not found - optional, only needed if you use
    echo     "gh auth login" for browser-based GitHub sign-in.
) else (
    echo [OK] GitHub CLI found.
)

echo.
echo ============================================
echo   All checks done. Launching GitForge Studio...
echo ============================================
echo.

python "%~dp0gitforge_studio.py"

if errorlevel 1 (
    echo.
    echo [X] App exited with an error. See above.
    pause
)
