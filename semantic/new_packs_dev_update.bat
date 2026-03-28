@echo off
setlocal

REM ============================================================
REM  Semantic Prompt - DEV: Build Database from Packs
REM ============================================================
REM
REM  PURPOSE:
REM    Converts JSON packs into the SQLite database.
REM    This is the "packs → DB" step used during development.
REM
REM  WHEN TO USE:
REM    - After editing or adding pack JSON files
REM    - When rebuilding the database from scratch
REM    - Before committing updates to the repo
REM
REM  WHAT IT DOES:
REM    - Scans semantic\packs\
REM    - Reads _meta + entries
REM    - Writes/updates category_meta.sqlite
REM
REM  IMPORTANT:
REM    - This is a DEV TOOL (not for end users)
REM    - Safe to run multiple times (idempotent)
REM    - Will overwrite existing DB entries for matching categories
REM
REM ============================================================

REM Get absolute path of this script's directory (semantic\)
set "ROOT=%~dp0"

echo.
echo ============================================================
echo   DEV: Building database from packs
echo ============================================================
echo ROOT: %ROOT%
echo.

REM ------------------------------------------------------------
REM OPTIONAL: Clean rebuild (uncomment if needed)
REM This deletes the DB before rebuilding from packs
REM ------------------------------------------------------------
REM if exist "%ROOT%meta\category_meta.sqlite" (
REM     echo Deleting existing database...
REM     del "%ROOT%meta\category_meta.sqlite"
REM )

REM ------------------------------------------------------------
REM Ensure packs folder exists
REM ------------------------------------------------------------
if not exist "%ROOT%packs" (
    echo ERROR: packs folder not found:
    echo   %ROOT%packs
    echo.
    echo This script expects existing JSON packs.
    pause
    exit /b 1
)

REM ------------------------------------------------------------
REM Run JSON → DB sync
REM ------------------------------------------------------------
echo Syncing packs to database...
echo.

python "%ROOT%tools\core\pack_catalog_sync.py" sync-json-to-db ^
  --packs-root "%ROOT%packs" ^
  --db "%ROOT%meta\category_meta.sqlite" ^
  --apply ^
  --backup

if errorlevel 1 (
    echo.
    echo ERROR: Database build failed.
    echo Check output above.
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   SUCCESS: Database updated from packs
echo ============================================================
echo.

REM ------------------------------------------------------------
REM Optional: quick reminder for next step
REM ------------------------------------------------------------
echo Next step (if testing install):
echo   Run install script to rebuild packs from DB
echo.

pause
exit /b 0