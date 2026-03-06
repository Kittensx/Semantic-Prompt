@echo off
python random_prompt_packs.py ^
  --packs .\packs ^
  --total 9 ^
  --max-per-category 1 ^
  --include-only panties_coverage panties_cut panties_design_accessories panties_leg_opening panties_rise panties_side panties_waistband_style panties_structure panties_trim^
  --other-random 0 ^
  --prints 100^
  --out panties.txt

pause