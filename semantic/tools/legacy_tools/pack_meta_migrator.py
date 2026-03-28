from __future__ import annotations

import argparse
import json
import random
import sqlite3
import string
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

JsonDict = Dict[str, Any]

DEFAULT_REQUIRED_META_FIELDS = [
    "category",
    "title",
    "generator_family",
    "generator_slot",
    "generatable",
    "parents",
    "children",
    "related_categories",
    "aliases",
    "search_tags",
]

CATEGORY_OVERRIDES: Dict[str, str] = {
    # "clothing/clothing_closure.json": "clothing.modifiers.closure",
    # "clothing_closure": "clothing.modifiers.closure",
}


@dataclass
class ScanRecord:
    path: Path
    rel_path: str
    category: str
    cat_id: str
    meta: JsonDict
    entry_keys: List[str]


def _read_json(path: Path) -> JsonDict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: JsonDict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _backup(path: Path) -> Path:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    bak = path.with_suffix(path.suffix + f".bak_{ts}")
    bak.write_bytes(path.read_bytes())
    return bak


def _norm_segment(text: str) -> str:
    import re

    text = (text or "").strip().lower()
    text = text.replace("-", "_")
    text = re.sub(r"[^a-z0-9_./\\]+", "_", text)
    text = text.replace("\\", "/")
    text = text.replace("/", ".")
    text = re.sub(r"_+", "_", text)
    text = re.sub(r"\.+", ".", text)
    return text.strip("._")


def _split_dot(cat: str) -> List[str]:
    return [p for p in _norm_segment(cat).split(".") if p]


def _path_parts_under_root(packs_root: Path, file_path: Path) -> List[str]:
    rel = file_path.resolve().relative_to(packs_root.resolve())
    return [_norm_segment(p) for p in rel.parent.parts if _norm_segment(p)]


def _normalize_leaf_stem(stem: str, last_folder: str) -> List[str]:
    stem = _norm_segment(stem)
    if not stem:
        return []
    if last_folder:
        if stem == last_folder:
            stem = ""
        elif stem.startswith(last_folder + "_"):
            stem = stem[len(last_folder) + 1 :]
        elif stem.startswith(last_folder + "."):
            stem = stem[len(last_folder) + 1 :]
    return [p for p in stem.replace("_", ".").split(".") if p]


def derive_category(packs_root: Path, file_path: Path, overrides: Optional[Dict[str, str]] = None) -> str:
    overrides = overrides or {}
    rel = file_path.resolve().relative_to(packs_root.resolve())
    rel_key = rel.as_posix()
    stem_key = _norm_segment(file_path.stem)

    if rel_key in overrides:
        return _norm_segment(overrides[rel_key])
    if stem_key in overrides:
        return _norm_segment(overrides[stem_key])

    folder_parts = _path_parts_under_root(packs_root, file_path)
    last_folder = folder_parts[-1] if folder_parts else ""
    leaf_parts = _normalize_leaf_stem(file_path.stem, last_folder)
    cat = ".".join([p for p in (folder_parts + leaf_parts) if p])

    if cat in overrides:
        return _norm_segment(overrides[cat])
    return cat


def title_from_category(category: str) -> str:
    parts = _split_dot(category)
    if not parts:
        return category
    use = parts[-2:] if len(parts) >= 2 else parts
    words: List[str] = []
    for part in use:
        words.extend(w.capitalize() for w in part.split("_") if w)
    return " ".join(words) if words else category


def generator_fields_from_category(category: str) -> Tuple[Optional[str], Optional[str]]:
    parts = _split_dot(category)
    if len(parts) < 2:
        return None, None
    return ".".join(parts[:-1]), parts[-1]


def normalize_list_str(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out: List[str] = []
    seen: Set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        s = item.strip()
        if not s:
            continue
        sl = s.lower()
        if sl in seen:
            continue
        seen.add(sl)
        out.append(s)
    return out


def _normalize_scalar(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


def _normalize_meta_value(field: str, value: Any) -> Any:
    list_fields = {"parents", "children", "related_categories", "aliases", "search_tags", "pack_paths"}
    bool_fields = {"generatable"}
    if field in list_fields:
        return normalize_list_str(value)
    if field in bool_fields:
        return bool(value) if value is not None else False
    return _normalize_scalar(value)


def ensure_meta_shape(meta: JsonDict, required_fields: Iterable[str]) -> JsonDict:
    shaped: JsonDict = {}
    for field in required_fields:
        default: Any = [] if field in {"parents", "children", "related_categories", "aliases", "search_tags", "pack_paths"} else None
        if field == "generatable":
            default = False
        shaped[field] = _normalize_meta_value(field, meta.get(field, default))
    for field, value in meta.items():
        if field not in shaped:
            shaped[field] = _normalize_meta_value(field, value)
    return shaped


def collect_meta_fields(files: Iterable[Path]) -> List[str]:
    fields: Set[str] = set(DEFAULT_REQUIRED_META_FIELDS)
    for fp in files:
        try:
            data = _read_json(fp)
        except Exception:
            continue
        meta = data.get("_meta")
        if isinstance(meta, dict):
            fields.update(str(k) for k in meta.keys() if isinstance(k, str) and k.strip())
    fields.discard("cat_id")
    return sorted(fields)


def generate_cat_id(existing_ids: Set[str], length: int = 12, prefix: str = "cat_") -> str:
    alphabet = string.ascii_lowercase + string.digits
    while True:
        suffix = "".join(random.choice(alphabet) for _ in range(length))
        cat_id = prefix + suffix
        if cat_id not in existing_ids:
            existing_ids.add(cat_id)
            return cat_id


def _build_canonical_meta(
    *,
    file_path: Path,
    rel_path: str,
    existing_meta: JsonDict,
    category: str,
    required_fields: List[str],
) -> JsonDict:
    meta = dict(existing_meta)
    meta["category"] = category
    meta.setdefault("title", title_from_category(category))

    family, slot = generator_fields_from_category(category)
    if family and not meta.get("generator_family"):
        meta["generator_family"] = family
    if slot and not meta.get("generator_slot"):
        meta["generator_slot"] = slot
    if "generatable" not in meta:
        meta["generatable"] = True

    meta.setdefault("parents", [])
    meta.setdefault("children", [])
    meta.setdefault("related_categories", [])
    meta.setdefault("aliases", [])
    meta.setdefault("search_tags", [])
    meta.setdefault("pack_paths", [rel_path])

    shaped = ensure_meta_shape(meta, required_fields)
    shaped["pack_paths"] = normalize_list_str(shaped.get("pack_paths", []) + [rel_path])
    return shaped


def _iter_pack_files(packs_root: Path) -> List[Path]:
    return sorted([p for p in packs_root.rglob("*.json") if p.is_file()])


def scan_packs(
    packs_root: Path,
    *,
    db_path: Path,
    overrides: Optional[Dict[str, str]] = None,
    required_fields: Optional[List[str]] = None,
) -> Tuple[List[ScanRecord], List[str]]:
    files = _iter_pack_files(packs_root)
    all_meta_fields = required_fields or collect_meta_fields(files)

    category_to_existing_cat_id = load_existing_category_map(db_path)
    existing_ids = load_existing_cat_ids(db_path)

    records: List[ScanRecord] = []

    for fp in files:
        data = _read_json(fp)
        if not isinstance(data, dict):
            continue

        meta = data.get("_meta") if isinstance(data.get("_meta"), dict) else {}
        rel_path = fp.resolve().relative_to(packs_root.resolve()).as_posix()
        category = derive_category(packs_root, fp, overrides=overrides)
        cat_id = str(meta.get("cat_id") or "").strip()

        if category in category_to_existing_cat_id:
            cat_id = category_to_existing_cat_id[category]
        elif not cat_id:
            cat_id = generate_cat_id(existing_ids)
            category_to_existing_cat_id[category] = cat_id
        else:
            if cat_id in existing_ids:
                category_to_existing_cat_id.setdefault(category, cat_id)
            else:
                existing_ids.add(cat_id)
                category_to_existing_cat_id[category] = cat_id

        canon_meta = _build_canonical_meta(
            file_path=fp,
            rel_path=rel_path,
            existing_meta=meta,
            category=category,
            required_fields=all_meta_fields,
        )

        entry_keys = [k for k in data.keys() if isinstance(k, str) and not k.startswith("_")]
        records.append(
            ScanRecord(
                path=fp,
                rel_path=rel_path,
                category=category,
                cat_id=cat_id,
                meta=canon_meta,
                entry_keys=sorted(entry_keys),
            )
        )

    return records, all_meta_fields


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS category_meta (
            cat_id TEXT PRIMARY KEY,
            category TEXT NOT NULL UNIQUE,
            meta_json TEXT NOT NULL,
            meta_fields_json TEXT NOT NULL,
            pack_paths_json TEXT NOT NULL,
            entry_keys_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meta_schema (
            schema_key TEXT PRIMARY KEY,
            schema_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def load_existing_cat_ids(db_path: Path) -> Set[str]:
    if not db_path.exists():
        return set()
    conn = sqlite3.connect(str(db_path))
    try:
        init_db(conn)
        rows = conn.execute("SELECT cat_id FROM category_meta").fetchall()
        return {str(r[0]) for r in rows}
    finally:
        conn.close()


def load_existing_category_map(db_path: Path) -> Dict[str, str]:
    if not db_path.exists():
        return {}
    conn = sqlite3.connect(str(db_path))
    try:
        init_db(conn)
        rows = conn.execute("SELECT category, cat_id FROM category_meta").fetchall()
        return {str(category): str(cat_id) for category, cat_id in rows}
    finally:
        conn.close()


def merge_records_by_cat_id(records: List[ScanRecord], all_fields: List[str]) -> Dict[str, ScanRecord]:
    merged: Dict[str, ScanRecord] = {}
    for rec in records:
        existing = merged.get(rec.cat_id)
        if existing is None:
            merged[rec.cat_id] = rec
            continue

        if existing.category != rec.category:
            raise ValueError(
                f"cat_id collision: {rec.cat_id} maps to both '{existing.category}' and '{rec.category}'"
            )

        # Merge meta while keeping the same shape.
        new_meta = ensure_meta_shape(existing.meta, all_fields)
        incoming = ensure_meta_shape(rec.meta, all_fields)
        for field in all_fields:
            old_val = new_meta.get(field)
            in_val = incoming.get(field)
            if isinstance(old_val, list) or isinstance(in_val, list):
                new_meta[field] = normalize_list_str((old_val or []) + (in_val or []))
            elif old_val in (None, "", False) and in_val not in (None, ""):
                new_meta[field] = in_val
        new_meta["pack_paths"] = normalize_list_str(new_meta.get("pack_paths", []) + [rec.rel_path])

        existing.meta = new_meta
        existing.entry_keys = sorted(set(existing.entry_keys) | set(rec.entry_keys))
    return merged


def write_db(db_path: Path, merged: Dict[str, ScanRecord], all_fields: List[str]) -> Dict[str, int]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        init_db(conn)
        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        conn.execute(
            "REPLACE INTO meta_schema(schema_key, schema_json, updated_at) VALUES (?, ?, ?)",
            ("category_meta_fields", json.dumps(all_fields, ensure_ascii=False), now),
        )

        count = 0
        for cat_id, rec in merged.items():
            meta_json = json.dumps(ensure_meta_shape(rec.meta, all_fields), ensure_ascii=False)
            pack_paths_json = json.dumps(sorted(set(rec.meta.get("pack_paths", [rec.rel_path]))), ensure_ascii=False)
            entry_keys_json = json.dumps(sorted(set(rec.entry_keys)), ensure_ascii=False)
            conn.execute(
                """
                REPLACE INTO category_meta(
                    cat_id, category, meta_json, meta_fields_json, pack_paths_json, entry_keys_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cat_id,
                    rec.category,
                    meta_json,
                    json.dumps(all_fields, ensure_ascii=False),
                    pack_paths_json,
                    entry_keys_json,
                    now,
                ),
            )
            count += 1
        conn.commit()
        return {"rows_written": count}
    finally:
        conn.close()


def write_cat_ids_back_to_packs(records: List[ScanRecord], *, backup: bool, dry_run: bool) -> Dict[str, int]:
    updated = 0
    unchanged = 0
    for rec in records:
        data = _read_json(rec.path)
        if not isinstance(data, dict):
            continue
        meta = data.get("_meta") if isinstance(data.get("_meta"), dict) else {}
        old = str(meta.get("cat_id") or "").strip()
        if old == rec.cat_id:
            unchanged += 1
            continue
        meta["cat_id"] = rec.cat_id
        data["_meta"] = meta
        if not dry_run:
            if backup:
                _backup(rec.path)
            _write_json(rec.path, data)
        updated += 1
    return {"packs_updated": updated, "packs_unchanged": unchanged}


def export_db_json(db_path: Path, out_json: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        init_db(conn)
        rows = conn.execute(
            "SELECT cat_id, category, meta_json, pack_paths_json, entry_keys_json, updated_at FROM category_meta ORDER BY category"
        ).fetchall()
        schema_row = conn.execute(
            "SELECT schema_json, updated_at FROM meta_schema WHERE schema_key = ?",
            ("category_meta_fields",),
        ).fetchone()
        out: JsonDict = {
            "_meta": {
                "exported_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "schema_fields": json.loads(schema_row[0]) if schema_row else [],
                "schema_updated_at": schema_row[1] if schema_row else None,
            }
        }
        for cat_id, category, meta_json, pack_paths_json, entry_keys_json, updated_at in rows:
            out[str(cat_id)] = {
                "category": category,
                "meta": json.loads(meta_json),
                "pack_paths": json.loads(pack_paths_json),
                "entry_keys": json.loads(entry_keys_json),
                "updated_at": updated_at,
            }
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Scan pack JSONs, discover _meta fields, assign cat_id, and migrate metadata into SQLite.")
    ap.add_argument("--packs-root", required=True, help="Root folder containing pack JSON files.")
    ap.add_argument("--db", required=True, help="SQLite database path to create/update.")
    ap.add_argument("--write-cat-id", action="store_true", help="Write _meta.cat_id back into each pack file.")
    ap.add_argument("--backup", action="store_true", help="Create .bak timestamped backups before writing pack files.")
    ap.add_argument("--dry-run", action="store_true", help="Do not modify pack files; still writes DB unless you skip that yourself.")
    ap.add_argument("--export-json", default=None, help="Optional JSON export of the SQLite contents.")
    args = ap.parse_args()

    packs_root = Path(args.packs_root).expanduser().resolve()
    db_path = Path(args.db).expanduser().resolve()

    if not packs_root.exists() or not packs_root.is_dir():
        raise SystemExit(f"Invalid --packs-root: {packs_root}")

    records, all_fields = scan_packs(
        packs_root,
        db_path=db_path,
        overrides=CATEGORY_OVERRIDES,
        required_fields=None,
    )

    merged = merge_records_by_cat_id(records, all_fields)
    db_report = write_db(db_path, merged, all_fields)

    file_report = {"packs_updated": 0, "packs_unchanged": 0}
    if args.write_cat_id:
        file_report = write_cat_ids_back_to_packs(records, backup=args.backup, dry_run=args.dry_run)

    if args.export_json:
        export_db_json(db_path, Path(args.export_json).expanduser().resolve())

    report = {
        "packs_scanned": len(records),
        "unique_categories": len({r.category for r in records}),
        "unique_cat_ids": len(merged),
        "discovered_meta_fields": all_fields,
        **db_report,
        **file_report,
        "db_path": str(db_path),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
