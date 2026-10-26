@echo off
setlocal
cd /d "%~dp0"

py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 goto run_py

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 goto run_python

echo MedNet needs Python 3.10 or newer.
echo Install Python from https://www.python.org/downloads/
echo During installation, enable the Python launcher or add Python to PATH.
echo Then close this window and double-click start_mednet.bat again.
echo No extra Python packages are required.
pause
exit /b 1

:run_py
echo Starting MedNet. Keep this window open while using the dashboard.
py -3 app.py
set "MEDNET_EXIT=%ERRORLEVEL%"
goto finish

:run_python
echo Starting MedNet. Keep this window open while using the dashboard.
python app.py
set "MEDNET_EXIT=%ERRORLEVEL%"

:finish
if "%MEDNET_EXIT%"=="0" exit /b 0
echo.
echo MedNet stopped with an error. Read the message above.
echo See START_HERE.md for setup and troubleshooting.
pause
exit /b %MEDNET_EXIT%
