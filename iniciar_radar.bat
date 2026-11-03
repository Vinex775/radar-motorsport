@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py main.py
) else (
    python main.py
)
echo.
echo APEX Motorsport Radar has stopped.
pause
