import json
from pathlib import Path


def category_to_path(category, cat_id):
    return Path(category.replace(".", "/")) / f"{cat_id}.json"


def export_bundle(db, bundle_id, out_root: Path):

    packs = db.get_bundle_packs(bundle_id)

    for cat_id, category, pack_json in packs:

        rel_path = category_to_path(category, cat_id)
        out_path = out_root / rel_path

        out_path.parent.mkdir(parents=True, exist_ok=True)

        data = json.loads(pack_json)

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")

        print("Exported:", rel_path)