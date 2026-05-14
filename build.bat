@echo off
echo ========================================
echo   Ninja Userbot - Build Native EXE
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found! Install Python 3.11+
    pause
    exit /b 1
)

REM Install dependencies
echo Installing dependencies...
python -m pip install --upgrade pip
pip install pyinstaller
pip install telethon httpx customtkinter Pillow cryptography

echo.
echo Building EXE...
echo.

REM Build with PyInstaller - no console, single file
pyinstaller --onefile --noconsole --name Ninja --clean app/ninja_gui.py

echo.
if exist "dist\Ninja.exe" (
    echo ========================================
    echo   SUCCESS! Native Windows EXE created:
    echo   dist\Ninja.exe
    echo ========================================
    echo.
    echo   This is a standalone Windows application.
    echo   No Python installation needed!
    echo ========================================
) else (
    echo ERROR: Build failed!
    echo Check the output above for errors.
)

pause
