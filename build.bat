@echo off
echo Building Ninja Bot...
cd /d "%~dp0bootstrap"
pyinstaller --onefile --noconsole --name ninja launcher.py
echo.
echo Build complete! EXE is in: bootstrap\dist\ninja.exe
pause
