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
  --total 15 ^
  --max-per-category 1 ^
  --include-min core.subject core.lighting core.palette physical.breasts physical.ethnicity clothing.state physical.generic_age physical.breasts.shape^
  --other-random 6 ^
  --prints 100^
  --out anything_prompts.txt

pause