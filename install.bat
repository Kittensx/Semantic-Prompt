@echo off
setlocal

REM Get path to this BAT file (same folder as install.py)
set "ROOT=%~dp0"

echo Running install.py...
echo.

python "%ROOT%install.py"

if errorlevel 1 (
    echo.
    echo ERROR: install.py failed.
    echo.
    pause
    exit /b 1
)

echo.
echo Install complete.
echo.

pause
exit /b 0