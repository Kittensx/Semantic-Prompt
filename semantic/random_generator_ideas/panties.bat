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
  --include-only clothing.garments.underwear.panties.mod.coverage clothing.garments.underwear.panties.mod.cut clothing.garments.underwear.panties.mod.accessories clothing.garments.underwear.panties.mod.leg_opening clothing.garments.underwear.panties.mod.rise clothing.garments.underwear.panties.mod.side clothing.garments.underwear.panties.mod.waistband_style clothing.garments.underwear.panties.mod.structure clothing.garments.underwear.panties.mod.trim^
  --other-random 0 ^
  --prints 100^
  --out panties.txt

pause
