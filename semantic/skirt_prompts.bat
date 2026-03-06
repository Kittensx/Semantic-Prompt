@echo off
python random_prompt_packs.py ^
  --packs .\packs ^
  --total 10 ^
  --max-per-category 1 ^
  --include-only skirt_cut skirt_details skirt_fasteners skirt_hem  skirt_length skirt_pattern skirt_pleats skirt_style skirt_volume skirt_waist ^
  --other-random 0 ^
  --prints 100^
  --out skirt_prompts.txt

pause