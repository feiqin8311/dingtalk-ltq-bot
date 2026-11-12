@echo off
setlocal
cd /d "%~dp0"

where conda >nul 2>nul
if errorlevel 1 (
    echo Conda was not found in PATH. Install Miniconda/Anaconda or add conda to PATH.
    pause
    exit /b 1
)

set "DINGTALK_PYTHON_EXE=python"
call conda run --no-capture-output -n dingtalk-bot powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher\start_all.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo Logistics bot launcher exited with code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%
