@echo off
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel% == 0 (
  set "PY=py -3"
) else (
  set "PY=python"
)
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv
  if errorlevel 1 goto :fail
)
.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :fail
.venv\Scripts\python.exe start.py
goto :eof
:fail
echo Setup failed. Check that Python 3 is installed and you have an internet connection.
pause
