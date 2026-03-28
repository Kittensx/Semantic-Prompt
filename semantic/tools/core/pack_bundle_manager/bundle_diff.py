import json
import hashlib


def file_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def diff_bundle_vs_folder(db, bundle_id, packs_root):

    packs = db.get_bundle_packs(bundle_id)

    for cat_id, category, pack_json in packs:

        expected_path = packs_root / category.replace(".", "/") / f"{cat_id}.json"

        if not expected_path.exists():
            print("Missing:", expected_path)
            continue

        with open(expected_path, "r", encoding="utf-8") as f:
            local_data = json.load(f)

        local_json = json.dumps(local_data, ensure_ascii=False, indent=2)

        if hashlib.sha256(local_json.encode()).hexdigest() != hashlib.sha256(pack_json.encode()).hexdigest():
            print("Modified:", expected_path)
        else:
            print("Match:", expected_path)