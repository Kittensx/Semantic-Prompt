@echo off
setlocal

REM ============================================================
REM  Semantic Prompt - USER INSTALL: Rebuild Packs from Database
REM ============================================================
REM
REM  PURPOSE:
REM    Recreates the JSON pack files from the shipped SQLite database.
REM    This is the "DB → packs" step used for installation.
REM
REM  WHEN TO USE:
REM    - After downloading / extracting the extension
REM    - If the packs folder is missing
REM    - If pack files need to be regenerated from the database
REM
REM  WHAT IT DOES:
REM    - Ensures semantic\packs\ exists
REM    - Reads semantic\meta\category_meta.sqlite
REM    - Writes canonical JSON packs into semantic\packs\
REM
REM  IMPORTANT:
REM    - This is the USER/INSTALL tool
REM    - It does not build the database from packs
REM    - It is safe to rerun if packs need to be restored
REM    - Existing files may be backed up before changes
REM
REM ============================================================

REM Get absolute path of this script's directory (semantic\)
set "ROOT=%~dp0"

echo.
echo ============================================================
echo   USER INSTALL: Rebuilding packs from database
echo ============================================================
echo ROOT: %ROOT%
echo.

REM ------------------------------------------------------------
REM Ensure packs folder exists
REM ------------------------------------------------------------
if not exist "%ROOT%packs" (
    echo Creating packs folder...
    mkdir "%ROOT%packs"
)

REM ------------------------------------------------------------
REM Verify database exists
REM ------------------------------------------------------------
if not exist "%ROOT%meta\category_meta.sqlite" (
    echo ERROR: Database not found:
    echo   %ROOT%meta\category_meta.sqlite
    echo.
    echo Make sure the database file is included with the extension.
    pause
    exit /b 1
)

REM ------------------------------------------------------------
REM Run DB → JSON sync
REM ------------------------------------------------------------
echo Rebuilding packs from database...
echo.

python "%ROOT%tools\core\pack_catalog_sync.py" sync-db-to-json ^
  --packs-root "%ROOT%packs" ^
  --db "%ROOT%meta\category_meta.sqlite" ^
  --apply ^
  --backup ^
  --no-cleanup-old

if errorlevel 1 (
    echo.
    echo ERROR: Pack install failed.
    echo Check output above.
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   SUCCESS: Packs rebuilt from database
echo ============================================================
echo.
echo You can now start the app.
echo.

pause
exit /b 0