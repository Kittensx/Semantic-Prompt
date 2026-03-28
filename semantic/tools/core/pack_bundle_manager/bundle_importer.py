import json
import hashlib
from pathlib import Path


def compute_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def import_from_packs(db, packs_root: Path, bundle_id: str):

    db.insert_bundle(bundle_id)

    for path in packs_root.rglob("*.json"):

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        meta = data.get("_meta", {})
        cat_id = meta.get("cat_id")
        category = meta.get("category")

        if not cat_id or not category:
            continue

        pack_json = json.dumps(data, ensure_ascii=False, indent=2)
        content_hash = compute_hash(pack_json)

        db.insert_pack(cat_id, category, pack_json, content_hash)
        db.add_pack_to_bundle(bundle_id, cat_id)

        print("Imported:", cat_id)