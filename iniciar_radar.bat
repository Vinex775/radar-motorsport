@echo off
setlocal EnableExtensions
cd /d "%~dp0"

call :find_python
if defined PYTHON_COMMAND goto run_apex

echo.
echo Python 3.10 or newer was not found on this computer.
echo APEX needs Python to run. No software will be installed without your approval.
echo.
choice /C YN /N /M "Would you like to install Python 3.14 now? [Y/N] "
if errorlevel 2 goto cancelled

where winget >nul 2>nul
if errorlevel 1 goto manual_install

echo.
echo Starting the official Python installation through Windows Package Manager...
echo Windows may ask for installation or permission confirmation.
winget install --id Python.Python.3.14 --exact --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto install_failed

call :find_python
if not defined PYTHON_COMMAND goto install_failed

goto run_apex

:manual_install
echo.
echo WinGet is not available on this computer.
echo The official Python downloads page will now open.
start "" "https://www.python.org/downloads/windows/"
echo Install Python 3.10 or newer, then run this file again.
goto finish

:install_failed
echo.
echo Python could not be detected after the installation attempt.
echo Please install Python 3.10 or newer from the official page:
start "" "https://www.python.org/downloads/windows/"
echo After installing, close this window and run iniciar_radar.bat again.
goto finish

:cancelled
echo.
echo Installation cancelled. No changes were made to your computer.
goto finish

:run_apex
echo.
echo Starting APEX Motorsport Radar...
%PYTHON_COMMAND% main.py
if errorlevel 1 (
    echo.
    echo APEX exited with an error. Check the message above.
)
echo.
echo APEX Motorsport Radar has stopped.
goto finish

:find_python
set "PYTHON_COMMAND="
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_COMMAND=py -3"
    exit /b 0
)
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_COMMAND=python"
    exit /b 0
)
if exist "%LocalAppData%\Programs\Python\Python314\python.exe" (
    "%LocalAppData%\Programs\Python\Python314\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_COMMAND="%LocalAppData%\Programs\Python\Python314\python.exe""
        exit /b 0
    )
)
exit /b 0

:finish
echo.
pause
endlocal
