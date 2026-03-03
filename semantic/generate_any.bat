@echo off
python random_prompt_packs.py ^
  --packs .\packs ^
  --total 15 ^
  --max-per-category 1 ^
  --include-min subject lighting palette breasts ethnicity clothing_state generic_age breasts_shape^
  --other-random 6 ^
  --prints 100^
  --out anything_prompts.txt

pause