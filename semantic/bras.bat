@echo off
python random_prompt_packs.py ^
  --packs .\packs ^
  --total 9 ^
  --max-per-category 1 ^
  --include-only bra_accessories bra_band bra_cup bra_straps bra_style bra_trim^
  --other-random 0 ^
  --prints 100^
  --out bras.txt

pause