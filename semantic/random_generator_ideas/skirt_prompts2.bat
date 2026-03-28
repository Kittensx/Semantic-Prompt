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
  --total 10 ^
  --max-per-category 1 ^
  --include-only skirt.mod.cut skirt.details skirt.fasteners skirt.hem  skirt.length skirt.pattern skirt.pleats skirt.style skirt.volume skirt.waist ^
  --other-random 0 ^
  --prints 100^
  --out skirt_prompts.txt

pause