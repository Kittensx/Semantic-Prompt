@echo off
setlocal

set "ROOT=%~dp0"

echo ROOT: %ROOT%

if not exist "%ROOT%packs" (
  echo Creating packs folder...
  mkdir "%ROOT%packs"
)

echo Syncing pack catalog JSON to database...

python tools/core/pack_catalog_sync.py sync-json-to-db --packs-root "packs" --db "meta/category_meta.sqlite" --apply
  

echo.
echo Sync complete.
pause
