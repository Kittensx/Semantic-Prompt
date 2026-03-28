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
  --include-only cat.appearance cat.coat_color cat.coat_pattern cat.ear_shape cat.eye_color cat.fangs cat.fur_length cat.nose cat.paws cat.tail cat.pose cat.tongue cat.whiskers^
  --other-random 0 ^
  --prints 100^
  --out cat.txt

pause