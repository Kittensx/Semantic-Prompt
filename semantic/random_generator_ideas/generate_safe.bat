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
  --total 12 ^
  --max-per-category 1 ^
  --include-min core.subject core.lighting core.palette physical.ethnicity ^
  --include-any core.composition core.quality backgrounds ^
  --other-random 8 ^
  --prints 100 ^
  --safe ^
  --out safe_prompts.txt

pause