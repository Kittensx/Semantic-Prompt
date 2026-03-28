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
  --total 8 ^
  --max-per-category 1 ^
  --include-only swim_onepiece.accessories swim_onepiece.back swim_onepiece.cut swim_onepiece.neckline swim_onepiece.panels swim_onepiece.straps clothing.material swim_onepiece.style ^
  --other-random 0 ^
  --prints 100^
  --out 1piece_prompts.txt

pause