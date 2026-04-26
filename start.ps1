Write-Host "========================================" -ForegroundColor Cyan
Write-Host "GeoDraft YOLO QA - Environment Check" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$pythonCmd = $null
$pythonFound = $false

$pythonPaths = @(
    "python",
    "python3",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
    "C:\Program Files\Python312\python.exe",
    "C:\Program Files\Python311\python.exe",
    "C:\Program Files\Python310\python.exe",
    "C:\Python312\python.exe",
    "C:\Python311\python.exe",
    "C:\Python310\python.exe"
)

foreach ($path in $pythonPaths) {
    try {
        if ($path -eq "python" -or $path -eq "python3") {
            $result = Get-Command $path -ErrorAction SilentlyContinue
            if ($result) {
                $fullPath = $result.Source
                if ($fullPath -notlike "*WindowsApps*") {
                    $pythonCmd = $fullPath
                    $pythonFound = $true
                    break
                }
            }
        } else {
            if (Test-Path $path -ErrorAction SilentlyContinue) {
                $pythonCmd = $path
                $pythonFound = $true
                break
            }
        }
    } catch {
        continue
    }
}

if (-not $pythonFound) {
    Write-Host "[ERROR] Python not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install Python 3.10+ from:" -ForegroundColor Yellow
    Write-Host "  https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Make sure to check 'Add Python to PATH' during installation." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[OK] Found Python at: $pythonCmd" -ForegroundColor Green
& $pythonCmd --version
Write-Host ""

if (-not (Test-Path ".venv")) {
    Write-Host "[INFO] Creating virtual environment..." -ForegroundColor Yellow
    & $pythonCmd -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to create virtual environment!" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-Host "[OK] Virtual environment created." -ForegroundColor Green
} else {
    Write-Host "[OK] Virtual environment already exists." -ForegroundColor Green
}

Write-Host ""
Write-Host "[INFO] Checking and installing dependencies..." -ForegroundColor Yellow
& ".\.venv\Scripts\pip.exe" install --upgrade pip -q
& ".\.venv\Scripts\pip.exe" install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to install dependencies!" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "[OK] Dependencies installed." -ForegroundColor Green

Write-Host ""
Write-Host "[INFO] Running environment self-check..." -ForegroundColor Yellow
$checkScript = @"
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
"@
& ".\.venv\Scripts\python.exe" -c $checkScript

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Starting GeoDraft YOLO QA..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Open your browser and visit:" -ForegroundColor Green
Write-Host "  http://127.0.0.1:5000" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop the server." -ForegroundColor Yellow
Write-Host ""

& ".\.venv\Scripts\python.exe" app.py
