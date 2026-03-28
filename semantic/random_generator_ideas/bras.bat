@echo off
setlocal

REM Get path to this BAT file
set "BASE=%~dp0"

REM Go UP one level (to semantic\)
set "ROOT=%BASE%.."

REM Normalize path
for %%I in ("%ROOT%") do set "ROOT=%%~fI"

echo ROOT: %ROOT%
echo.

python "%ROOT%\tools\core\random_prompt_packs.py" ^
  --packs .\packs ^
  --total 9 ^
  --max-per-category 1 ^
  --include-only clothing.garments.underwear.bras.mod.accessories clothing.garments.underwear.bras.mod.band clothing.garments.underwear.bras.mod.cup clothing.garments.underwear.bras.mod.straps clothing.garments.underwear.bras.mod.style clothing.garments.underwear.bras.mod.trim^
  --other-random 0 ^
  --prints 100^
  --out bras.txt

pause
