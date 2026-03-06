@echo off
python random_prompt_packs.py ^
  --packs .\packs ^
  --total 8 ^
  --max-per-category 1 ^
  --include-only swim_onepiece_accessories swim_onepiece_back swim_onepiece_cut swim_onepiece_neckline swim_onepiece_panels swim_onepiece_straps clothing_material swim_onepiece_style ^
  --other-random 0 ^
  --prints 100^
  --out 1piece_prompts.txt

pause