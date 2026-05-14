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
pip install pyinstaller
pip install -r app/requirements.txt

echo.
echo Building EXE...
echo.

REM Build with PyInstaller
pyinstaller --onefile --noconsole --name Ninja --clean app/ninja_gui.py

echo.
if exist "dist\Ninja.exe" (
    echo ========================================
    echo   SUCCESS! EXE created:
    echo   dist\Ninja.exe
    echo ========================================
) else (
    echo ERROR: Build failed!
)

pause
