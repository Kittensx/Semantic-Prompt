@echo off
setlocal

REM This BAT lives in semantic\
set "ROOT=%~dp0"

REM Normalize path
for %%I in ("%ROOT%") do set "ROOT=%%~fI"

echo ROOT: %ROOT%
echo.

REM Ensure packs folder exists
if not exist "%ROOT%\packs" (
    echo Creating packs folder...
    mkdir "%ROOT%\packs"
)

echo Looking for errors inside the packs folders for JSON files...
echo.

python "%ROOT%\tools\core\check_json.py" "%ROOT%\packs" --recursive

if errorlevel 1 (
    echo.
    echo JSON issues detected.
    echo Review output above.
    echo.
) else (
    echo.
    echo JSON OK - no issues found.
    echo.
)

echo Fix Complete
pause