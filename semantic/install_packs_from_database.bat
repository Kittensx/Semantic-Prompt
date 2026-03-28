@echo off
setlocal

set "ROOT=%~dp0"

echo ROOT: %ROOT%

if not exist "%ROOT%packs" (
  echo Creating packs folder...
  mkdir "%ROOT%packs"
)

python "%ROOT%tools\core\pack_catalog_sync.py" sync-db-to-json ^
  --packs-root "%ROOT%packs" ^
  --db "%ROOT%meta\category_meta.sqlite" ^
  --apply ^
  --backup ^
  --no-cleanup-old

pause