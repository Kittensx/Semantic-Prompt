@echo off
python random_prompt_packs.py ^
  --packs .\packs ^
  --total 2 ^
  --max-per-category 1 ^
  --include-only clothing_light_effects clothing_fit^
  --other-random 0 ^
  --prints 100^
  --out clothing_fit.txt

pause