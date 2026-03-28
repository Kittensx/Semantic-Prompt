import json
import math
from pathlib import Path

PACK_DIR = r"C:\Programs\A1111\stable-diffusion-webui\extensions\semantic_prompt\semantic\packs"

def count_pack_options(file_path: Path) -> int:
    try:
        text = file_path.read_text(encoding="utf-8")
        data = json.loads(text)
    except Exception as e:
        print(f"[SKIP] {file_path}  (json error: {e})")
        return 0

    keys = [k for k in data.keys() if not str(k).startswith("_")]
    if not keys:
        print(f"[SKIP] {file_path}  (no non-_ keys)")
        return 0

    return len(keys)

def main():
    pack_path = Path(PACK_DIR)

    print(f"PACK_DIR = {pack_path}")
    print(f"Exists?  {pack_path.exists()}")
    print(f"Is dir?  {pack_path.is_dir()}\n")

    json_files = list(pack_path.rglob("*.json")) if pack_path.exists() else []
    print(f"Found {len(json_files)} .json files\n")

    if len(json_files) > 0:
        print("First 20 files found:")
        for f in json_files[:20]:
            print(" -", f)
        print()

    pack_counts = {}
    total = 1

    for file in json_files:
        count = count_pack_options(file)
        if count == 0:
            continue
        pack_counts[file.stem] = count
        total *= count

    print("\nPack Option Counts")
    print("------------------")
    for name, count in sorted(pack_counts.items()):
        print(f"{name:30} {count}")

    print("\nTotal Possible Combinations")
    print("---------------------------")
    print(f"{total:,}")

    print("\nLog10 scale (order of magnitude)")
    print("---------------------------")
    if total > 0:
        print(f"10^{math.log10(total):.2f}")
    else:
        print("N/A")

if __name__ == "__main__":
    main()