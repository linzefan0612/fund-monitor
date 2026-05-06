@echo off
chcp 936 >nul
title Fund Monitor
color 0A

echo.
echo  ==================================================
echo.
echo           Fund Monitor - Starting
echo.
echo  ==================================================
echo.

echo [Step 1/5] Checking Python...

python --version >nul 2>&1
if errorlevel 1 (
    color 0C
    echo.
    echo  [Error] Python not found!
    echo.
    echo  Please install Python 3.8+ from:
    echo  https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo     [OK] Python: %PYTHON_VERSION%
echo.

echo [Step 2/5] Checking dependencies...

pip show flask >nul 2>&1
if errorlevel 1 (
    echo     Installing dependencies...
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        color 0C
        echo.
        echo  [Error] Failed to install dependencies
        pause
        exit /b 1
    )
)
echo     [OK] Dependencies ready
echo.

echo [Step 3/5] Checking port 5000...

set PORT_USED=0
netstat -ano | findstr ":5000" | findstr "LISTENING" >nul && set PORT_USED=1

if "%PORT_USED%"=="1" (
    color 0E
    echo.
    echo  [Warning] Port 5000 is in use!
    echo.
    echo  Options:
    echo  [1] Kill the process and continue
    echo  [2] Continue anyway
    echo  [3] Exit
    echo.
    set /p OPT="Choose (1/2/3): "

    if "%OPT%"=="1" (
        for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000" ^| findstr "LISTENING"') do (
            taskkill /F /PID %%a >nul 2>&1
        )
        echo     [OK] Process killed
        timeout /t 2 >nul
    )
    if "%OPT%"=="3" (
        exit /b 0
    )
) else (
    echo     [OK] Port 5000 available
)
echo.

echo [Step 4/5] Setting directory...

cd /d "%~dp0"
echo     [OK] Directory: %CD%
echo.

echo [Step 5/5] Starting server...
echo.
echo  ==================================================
echo.
echo     Server started!
echo.
echo     Open browser and visit:
echo.
echo     http://localhost:5000
echo.
echo     Press Ctrl+C to stop
echo.
echo  ==================================================
echo.

python app.py

if errorlevel 1 (
    color 0C
    echo.
    echo  [Error] Server failed to start
    echo  Check the error message above
    echo.
)

pause
