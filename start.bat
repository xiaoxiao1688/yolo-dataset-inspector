@echo off
setlocal enabledelayedexpansion

echo ========================================
echo GeoDraft YOLO QA - Environment Check
echo ========================================
echo.

set PYTHON_CMD=python
set PYTHON_FOUND=0

where python >nul 2>&1
if %errorlevel% equ 0 (
  for /f "tokens=*" %%i in ('where python 2^>nul') do (
    set "p=%%i"
    if not "!p:WindowsApps=!"=="!p!" (
      echo [WARN] Found Windows Store Python shortcut, skipping...
    ) else (
      set PYTHON_CMD=%%i
      set PYTHON_FOUND=1
      goto :python_found
    )
  )
)

if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe" (
  set PYTHON_CMD="C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe"
  set PYTHON_FOUND=1
  goto :python_found
)

if exist "C:\Program Files\Python312\python.exe" (
  set PYTHON_CMD="C:\Program Files\Python312\python.exe"
  set PYTHON_FOUND=1
  goto :python_found
)

if exist "C:\Python312\python.exe" (
  set PYTHON_CMD="C:\Python312\python.exe"
  set PYTHON_FOUND=1
  goto :python_found
)

:python_found
if %PYTHON_FOUND% equ 0 (
  echo [ERROR] Python not found!
  echo.
  echo Please install Python 3.10+ from:
  echo   https://www.python.org/downloads/
  echo.
  echo Make sure to check "Add Python to PATH" during installation.
  echo.
  pause
  exit /b 1
)

echo [OK] Found Python at: %PYTHON_CMD%
%PYTHON_CMD% --version
echo.

if not exist .venv (
  echo [INFO] Creating virtual environment...
  %PYTHON_CMD% -m venv .venv
  if %errorlevel% neq 0 (
    echo [ERROR] Failed to create virtual environment!
    pause
    exit /b 1
  )
  echo [OK] Virtual environment created.
) else (
  echo [OK] Virtual environment already exists.
)

echo.
echo [INFO] Checking and installing dependencies...
call .venv\Scripts\python -m pip install --upgrade pip -q
call .venv\Scripts\python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
  echo [ERROR] Failed to install dependencies!
  pause
  exit /b 1
)
echo [OK] Dependencies installed.

echo.
echo [INFO] Running environment self-check...
call .venv\Scripts\python -c "
import sys
import json

checks = {
    'python_version': '.'.join(map(str, sys.version_info[:3])),
    'python_path': sys.executable,
    'requirements': [],
    'status': 'ok'
}

required_packages = ['flask']
for pkg in required_packages:
    try:
        __import__(pkg)
        checks['requirements'].append({'package': pkg, 'status': 'ok'})
    except ImportError:
        checks['requirements'].append({'package': pkg, 'status': 'missing'})
        checks['status'] = 'error'

print(json.dumps(checks, indent=2))
"

echo.
echo ========================================
echo Starting GeoDraft YOLO QA...
echo ========================================
echo.
echo Open your browser and visit:
echo   http://127.0.0.1:5000
echo.
echo Press Ctrl+C to stop the server.
echo.

call .venv\Scripts\python app.py

endlocal
