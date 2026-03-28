import hashlib
import json


def compute_bundle_hash(bundle_packs):
    """
    bundle_packs: iterable of (cat_id, category, pack_json)
    """
    normalized = []
    for cat_id, category, pack_json in bundle_packs:
        normalized.append({
            "cat_id": cat_id,
            "category": category,
            "pack_json": json.loads(pack_json),
        })

    normalized.sort(key=lambda x: x["cat_id"])

    text = json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()