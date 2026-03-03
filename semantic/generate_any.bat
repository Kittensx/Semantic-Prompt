@echo off
python random_prompt_packs.py ^
  --packs .\packs ^
  --total 12 ^
  --max-per-category 1 ^
  --include-min subject lighting palette ethnicity hairstyles backgrounds^
  --other-random 8 ^
  --prints 100^
  --out anything_prompts.txt


pause
