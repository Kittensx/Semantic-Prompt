from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

JsonDict = Dict[str, Any]


@dataclass
class DbRecord:
    cat_id: str
    category: str
    meta: JsonDict
    pack_paths: List[str]
    entry_keys: List[str]


@dataclass
class SourcePack:
    path: Path
    rel_path: str
    cat_id: str
    data: JsonDict


# -----------------------------
# Basic helpers
# -----------------------------

def read_json(path: Path) -> JsonDict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: JsonDict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def backup_file(path: Path, backup_root: Path) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    rel = Path(str(path).replace(":", "_"))
    dest = backup_root / stamp / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
    return dest


def norm_segment(text: str) -> str:
    import re

    text = (text or "").strip().lower()
    text = text.replace("-", "_")
    text = re.sub(r"[^a-z0-9_.]+", "_", text)
    text = re.sub(r"_+", "_", text)
    text = re.sub(r"\.+", ".", text)
    return text.strip("._")


# -----------------------------
# DB loading
# -----------------------------

def load_db_records(db_path: Path) -> Dict[str, DbRecord]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT cat_id, category, meta_json, pack_paths_json, entry_keys_json FROM category_meta"
        ).fetchall()
    finally:
        conn.close()

    out: Dict[str, DbRecord] = {}
    for cat_id, category, meta_json, pack_paths_json, entry_keys_json in rows:
        meta = json.loads(meta_json) if meta_json else {}
        pack_paths = json.loads(pack_paths_json) if pack_paths_json else []
        entry_keys = json.loads(entry_keys_json) if entry_keys_json else []
        if not isinstance(meta, dict):
            raise ValueError(f"meta_json for {cat_id} is not an object")
        category = norm_segment(meta.get("category") or category)
        meta["category"] = category
        meta["cat_id"] = str(cat_id)
        out[str(cat_id)] = DbRecord(
            cat_id=str(cat_id),
            category=category,
            meta=meta,
            pack_paths=[str(p) for p in pack_paths],
            entry_keys=[str(k) for k in entry_keys],
        )
    return out


# -----------------------------
# Pack scanning and grouping
# -----------------------------

def iter_json_files(root: Path) -> List[Path]:
    return sorted([p for p in root.rglob("*.json") if p.is_file()])


def scan_source_packs(packs_root: Path) -> Tuple[List[SourcePack], List[str]]:
    source_packs: List[SourcePack] = []
    missing_cat_id: List[str] = []

    for path in iter_json_files(packs_root):
        try:
            data = read_json(path)
        except Exception as e:
            raise RuntimeError(f"Failed reading JSON: {path}: {e}") from e

        if not isinstance(data, dict):
            continue

        meta = data.get("_meta") if isinstance(data.get("_meta"), dict) else {}
        cat_id = str(meta.get("cat_id") or "").strip()
        rel_path = path.resolve().relative_to(packs_root.resolve()).as_posix()

        if not cat_id:
            missing_cat_id.append(rel_path)
            continue

        source_packs.append(SourcePack(path=path, rel_path=rel_path, cat_id=cat_id, data=data))

    return source_packs, missing_cat_id


# -----------------------------
# Sync logic
# -----------------------------

def destination_for_record(packs_root: Path, record: DbRecord) -> Path:
    parts = [p for p in record.category.split(".") if p]
    if not parts:
        raise ValueError(f"Empty category for cat_id {record.cat_id}")
    return packs_root.joinpath(*parts, f"{record.cat_id}.json")



def merge_pack_contents(record: DbRecord, packs: Iterable[SourcePack], strict_collisions: bool) -> JsonDict:
    merged: JsonDict = {"_meta": dict(record.meta)}
    merged["_meta"]["cat_id"] = record.cat_id
    merged["_meta"]["category"] = record.category

    collisions: List[str] = []

    for pack in sorted(packs, key=lambda p: p.rel_path):
        for key, value in pack.data.items():
            if not isinstance(key, str) or key.startswith("_"):
                continue
            if key in merged:
                if merged[key] == value:
                    continue
                collisions.append(f"{record.cat_id}: entry key collision for '{key}' from {pack.rel_path}")
                if strict_collisions:
                    raise ValueError(collisions[-1])
            merged[key] = value

    if collisions and not strict_collisions:
        merged.setdefault("_sync_warnings", collisions)

    return merged



def remove_empty_dirs(start_dir: Path, stop_dir: Path) -> None:
    cur = start_dir
    stop_dir = stop_dir.resolve()
    while cur.resolve() != stop_dir:
        try:
            cur.rmdir()
        except OSError:
            break
        cur = cur.parent



def sync_packs(
    *,
    packs_root: Path,
    db_path: Path,
    backup: bool,
    dry_run: bool,
    cleanup_old: bool,
    strict_collisions: bool,
) -> Dict[str, Any]:
    db_records = load_db_records(db_path)
    source_packs, missing_cat_id = scan_source_packs(packs_root)

    by_cat_id: Dict[str, List[SourcePack]] = {}
    for pack in source_packs:
        by_cat_id.setdefault(pack.cat_id, []).append(pack)

    unknown_cat_ids = sorted([cid for cid in by_cat_id if cid not in db_records])
    if unknown_cat_ids:
        preview = ", ".join(unknown_cat_ids[:10])
        raise RuntimeError(f"Found cat_id values in packs that are missing from DB: {preview}")

    backup_root = packs_root.parent / "backups" / "pack_sync_from_db"
    written: List[str] = []
    removed: List[str] = []
    skipped_db_only: List[str] = []
    merged_count = 0

    for cat_id, record in sorted(db_records.items(), key=lambda kv: kv[1].category):
        source_group = by_cat_id.get(cat_id, [])
        if not source_group:
            skipped_db_only.append(cat_id)
            continue

        if len(source_group) > 1:
            merged_count += len(source_group) - 1

        dest = destination_for_record(packs_root, record)
        merged_data = merge_pack_contents(record, source_group, strict_collisions=strict_collisions)

        if not dry_run:
            for pack in source_group:
                if backup:
                    backup_file(pack.path, backup_root)

            write_json(dest, merged_data)
            written.append(dest.resolve().relative_to(packs_root.resolve()).as_posix())

            if cleanup_old:
                source_paths = {p.path.resolve() for p in source_group}
                for src in source_group:
                    if src.path.resolve() == dest.resolve():
                        continue
                    src.path.unlink(missing_ok=True)
                    removed.append(src.rel_path)
                    remove_empty_dirs(src.path.parent, packs_root)

                # If dest reused one existing file path but the name/path changed, old file was already overwritten via new dest.
                # Remove old source if it differs.
                if dest.resolve() not in source_paths:
                    for src in source_group:
                        if src.path.exists():
                            src.path.unlink(missing_ok=True)
                            if src.rel_path not in removed:
                                removed.append(src.rel_path)
                            remove_empty_dirs(src.path.parent, packs_root)
        else:
            written.append(dest.resolve().relative_to(packs_root.resolve()).as_posix())
            if cleanup_old:
                for src in source_group:
                    if src.path.resolve() != dest.resolve():
                        removed.append(src.rel_path)

    return {
        "db_records": len(db_records),
        "source_packs": len(source_packs),
        "missing_cat_id": missing_cat_id,
        "unknown_cat_ids": unknown_cat_ids,
        "written_paths": written,
        "removed_paths": removed,
        "db_only_cat_ids": skipped_db_only,
        "merged_sources": merged_count,
        "backup_root": str(backup_root),
    }


# -----------------------------
# CLI
# -----------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Rewrite pack files from category_meta.sqlite, place them under category-based folders, "
            "and rename each file to <cat_id>.json."
        )
    )
    ap.add_argument("--packs-root", required=True, help="Root packs folder, e.g. semantic/packs")
    ap.add_argument("--db", required=True, help="Path to category_meta.sqlite")
    ap.add_argument("--backup", action="store_true", help="Back up source files before any write/delete")
    ap.add_argument("--dry-run", action="store_true", help="Preview actions without modifying files")
    ap.add_argument(
        "--no-cleanup-old",
        action="store_true",
        help="Write synced files but keep old source files in place",
    )
    ap.add_argument(
        "--strict-collisions",
        action="store_true",
        help="Fail if two source files for the same cat_id contain different values under the same entry key",
    )
    ap.add_argument(
        "--report-json",
        default=None,
        help="Optional path to write a JSON report of actions taken",
    )
    args = ap.parse_args()

    packs_root = Path(args.packs_root).expanduser().resolve()
    db_path = Path(args.db).expanduser().resolve()

    if not packs_root.exists() or not packs_root.is_dir():
        raise SystemExit(f"Invalid --packs-root: {packs_root}")
    if not db_path.exists() or not db_path.is_file():
        raise SystemExit(f"Invalid --db: {db_path}")

    report = sync_packs(
        packs_root=packs_root,
        db_path=db_path,
        backup=args.backup,
        dry_run=args.dry_run,
        cleanup_old=not args.no_cleanup_old,
        strict_collisions=args.strict_collisions,
    )

    if args.report_json:
        out = Path(args.report_json).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    preview_written = report["written_paths"][:10]
    preview_removed = report["removed_paths"][:10]

    print(json.dumps({
        "db_records": report["db_records"],
        "source_packs": report["source_packs"],
        "missing_cat_id_count": len(report["missing_cat_id"]),
        "unknown_cat_id_count": len(report["unknown_cat_ids"]),
        "written_count": len(report["written_paths"]),
        "removed_count": len(report["removed_paths"]),
        "db_only_count": len(report["db_only_cat_ids"]),
        "merged_sources": report["merged_sources"],
        "written_preview": preview_written,
        "removed_preview": preview_removed,
        "backup_root": report["backup_root"],
        "dry_run": args.dry_run,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
