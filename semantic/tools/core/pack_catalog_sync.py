from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import sqlite3
import string
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

JsonDict = Dict[str, Any]
LIST_META_FIELDS = {
    "parents",
    "children",
    "related_categories",
    "aliases",
    "search_tags",
    "pack_paths",
}
BOOL_META_FIELDS = {"generatable"}
MIN_REQUIRED_META_FIELDS = ["category", "title", "notes"]
DEFAULT_OPTIONAL_META_FIELDS = [
    "generator_family",
    "generator_slot",
    "generatable",
    "parents",
    "children",
    "related_categories",
    "aliases",
    "search_tags",
    "pack_paths",
    "schema_version",
]
DEFAULT_META_SCHEMA = MIN_REQUIRED_META_FIELDS + DEFAULT_OPTIONAL_META_FIELDS


# -----------------------------
# Data models
# -----------------------------

@dataclass
class PackState:
    path: Path
    rel_path: str
    data: JsonDict
    meta: JsonDict
    entry_keys: List[str]
    cat_id: str
    file_category: str
    path_category: str
    db_category: Optional[str]
    exists_in_db: bool
    is_new_to_db: bool


@dataclass
class PlannedAction:
    source_rel_path: str
    category: str
    cat_id: str
    dest_rel_path: str
    resolution: str
    db_action: str
    json_action: str
    move_required: bool
    missing_fields_added: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return {
            "source_rel_path": self.source_rel_path,
            "category": self.category,
            "cat_id": self.cat_id,
            "dest_rel_path": self.dest_rel_path,
            "resolution": self.resolution,
            "db_action": self.db_action,
            "json_action": self.json_action,
            "move_required": self.move_required,
            "missing_fields_added": list(self.missing_fields_added),
            "warnings": list(self.warnings),
        }

@dataclass
class ConflictRecord:
    reason: str
    source_rel_paths: List[str] = field(default_factory=list)
    category: Optional[str] = None
    cat_id: Optional[str] = None
    extra: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return {
            "reason": self.reason,
            "source_rel_paths": list(self.source_rel_paths),
            "category": self.category,
            "cat_id": self.cat_id,
            "extra": dict(self.extra),
        }
        
@dataclass
class SyncPlan:
    mode: str
    actions: List[PlannedAction] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    conflict_records: List[ConflictRecord] = field(default_factory=list)
    conflicted_rel_paths: set[str] = field(default_factory=set)
    warnings: List[str] = field(default_factory=list)

    def add_conflict(
        self,
        reason: str,
        *,
        source_rel_paths: Optional[Sequence[str]] = None,
        category: Optional[str] = None,
        cat_id: Optional[str] = None,
        extra: Optional[JsonDict] = None,
    ) -> None:
        self.conflicts.append(reason)

        record = ConflictRecord(
            reason=reason,
            source_rel_paths=list(source_rel_paths or []),
            category=category,
            cat_id=cat_id,
            extra=dict(extra or {}),
        )
        self.conflict_records.append(record)

        for rel_path in record.source_rel_paths:
            if rel_path and rel_path != "<db-only>":
                self.conflicted_rel_paths.add(rel_path)

    def summary(self) -> JsonDict:
        return {
            "mode": self.mode,
            "items": len(self.actions),
            "conflicts": len(self.conflicts),
            "warnings": len(self.warnings),
            "db_inserts": sum(1 for a in self.actions if a.db_action == "insert"),
            "db_updates": sum(1 for a in self.actions if a.db_action == "update"),
            "json_updates": sum(1 for a in self.actions if a.json_action != "skip"),
            "moves": sum(1 for a in self.actions if a.move_required),
        }

    def to_report(self) -> JsonDict:
        return {
            "summary": self.summary(),
            "conflicts": list(self.conflicts),
            "conflict_records": [c.to_dict() for c in self.conflict_records],
            "conflicted_rel_paths": sorted(self.conflicted_rel_paths),
            "warnings": list(self.warnings),
            "actions": [a.to_dict() for a in self.actions],
        }


# -----------------------------
# Helpers
# -----------------------------


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")



def read_json(path: Path) -> JsonDict:
    return json.loads(path.read_text(encoding="utf-8"))



def write_json(path: Path, data: JsonDict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")



def norm_segment(text: str) -> str:
    text = (text or "").strip().lower()
    text = text.replace("-", "_")
    text = text.replace("\\", "/")
    text = re.sub(r"[^a-z0-9_./]+", "_", text)
    text = re.sub(r"_+", "_", text)
    text = re.sub(r"\.+", ".", text)
    return text.strip("._/")



def normalize_category(category: str) -> str:
    return norm_segment(category).replace("/", ".")



def split_category(category: str) -> List[str]:
    return [p for p in normalize_category(category).split(".") if p]



def category_to_relpath(category: str, cat_id: str) -> str:
    parts = split_category(category)
    if not parts:
        raise ValueError("Category is empty after normalization")
    return "/".join(parts + [f"{cat_id}.json"])



def title_from_category(category: str) -> str:
    parts = split_category(category)
    if not parts:
        return "Untitled Pack"
    use = parts[-2:] if len(parts) >= 2 else parts
    out: List[str] = []
    for part in use:
        out.extend(token.capitalize() for token in part.split("_") if token)
    return " ".join(out) or "Untitled Pack"



def notes_from_category(category: str) -> str:
    return f"Pack contents for {category}."



def generator_fields_from_category(category: str) -> Tuple[Optional[str], Optional[str]]:
    parts = split_category(category)
    if len(parts) < 2:
        return None, parts[-1] if parts else None
    return ".".join(parts[:-1]), parts[-1]



def normalize_list_str(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out: List[str] = []
    seen = set()
    for item in value:
        if not isinstance(item, str):
            continue
        s = item.strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out



def normalize_meta_value(field: str, value: Any) -> Any:
    if field in LIST_META_FIELDS:
        return normalize_list_str(value)
    if field in BOOL_META_FIELDS:
        return bool(value) if value is not None else False
    if isinstance(value, str):
        return value.strip()
    return value



def ensure_meta_shape(meta: JsonDict, rel_path: str, schema_fields: Sequence[str]) -> Tuple[JsonDict, List[str]]:
    meta = dict(meta or {})
    added: List[str] = []

    if not meta.get("title"):
        meta["title"] = title_from_category(str(meta.get("category") or ""))
        added.append("title")
    if not meta.get("notes"):
        meta["notes"] = notes_from_category(str(meta.get("category") or ""))
        added.append("notes")

    family, slot = generator_fields_from_category(str(meta.get("category") or ""))
    if family and not meta.get("generator_family"):
        meta["generator_family"] = family
        added.append("generator_family")
    if slot and not meta.get("generator_slot"):
        meta["generator_slot"] = slot
        added.append("generator_slot")

    if "generatable" not in meta:
        meta["generatable"] = True
        added.append("generatable")
    if "schema_version" not in meta:
        meta["schema_version"] = 1
        added.append("schema_version")

    for name in LIST_META_FIELDS:
        if name == "pack_paths":
            # pack_paths should represent the canonical current on-disk path,
            # not a history of all prior locations.
            if name not in meta:
                added.append(name)
            meta[name] = [rel_path]
        else:
            if name not in meta:
                meta[name] = []
                added.append(name)

    shaped: JsonDict = {}
    for field in schema_fields:
        if field == "category":
            val = normalize_category(str(meta.get("category") or ""))
        else:
            val = meta.get(field)
        if field not in meta:
            if field in LIST_META_FIELDS:
                val = []
            elif field == "generatable":
                val = False
            else:
                val = None
        shaped[field] = normalize_meta_value(field, val)

    for key, value in meta.items():
        if key not in shaped:
            shaped[key] = normalize_meta_value(key, value)

    if shaped.get("pack_paths") is not None:
        shaped["pack_paths"] = [rel_path]
    return shaped, sorted(set(added))



def derive_category_from_path(packs_root: Path, file_path: Path) -> str:
    rel = file_path.resolve().relative_to(packs_root.resolve())
    folder_parts = [norm_segment(p) for p in rel.parent.parts if norm_segment(p)]
    stem = norm_segment(file_path.stem)
    last_folder = folder_parts[-1] if folder_parts else ""
    leaf = stem
    if stem.startswith("cat_"):
        leaf = ""
    elif last_folder and stem == last_folder:
        leaf = ""
    elif last_folder and stem.startswith(last_folder + "_"):
        leaf = stem[len(last_folder) + 1 :]
    elif last_folder and stem.startswith(last_folder + "."):
        leaf = stem[len(last_folder) + 1 :]
    leaf_parts = [p for p in leaf.replace("_", ".").split(".") if p]
    category = ".".join(folder_parts + leaf_parts)
    return normalize_category(category)



def iter_json_files(root: Path) -> List[Path]:
    return sorted(p for p in root.rglob("*.json") if p.is_file())



def gen_cat_id(existing: set[str]) -> str:
    alphabet = string.ascii_lowercase + string.digits
    while True:
        cid = "cat_" + "".join(random.choice(alphabet) for _ in range(12))
        if cid not in existing:
            existing.add(cid)
            return cid



def backup_copy(path: Path, backup_root: Path) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    rel = Path(*path.parts[1:]) if path.is_absolute() else path
    rel = Path(str(rel).replace(":", "_"))
    dest = backup_root / stamp / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
    return dest



def remove_empty_dirs(start_dir: Path, stop_dir: Path) -> None:
    cur = start_dir.resolve()
    stop = stop_dir.resolve()
    while cur != stop:
        try:
            cur.rmdir()
        except OSError:
            break
        cur = cur.parent

def get_conflict_review_root(packs_root: Path) -> Path:
    return packs_root.parent / "conflicts" / "pack_catalog_sync"


def isolate_conflicted_files(
    *,
    packs_root: Path,
    states: Sequence[PackState],
    conflict_records: Sequence[ConflictRecord],
    move_files: bool = False,
) -> JsonDict:
    review_root = get_conflict_review_root(packs_root)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_root = review_root / stamp
    files_root = run_root / "files"
    manifest_path = run_root / "manifest.json"

    path_to_state = {s.rel_path: s for s in states}
    copied: List[str] = []
    moved: List[str] = []
    missing: List[str] = []

    for rel_path in sorted({rel for rec in conflict_records for rel in rec.source_rel_paths if rel}):
        state = path_to_state.get(rel_path)
        if state is None or not state.path.exists():
            missing.append(rel_path)
            continue

        dest = files_root / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        if move_files:
            shutil.move(str(state.path), str(dest))
            remove_empty_dirs(state.path.parent, packs_root)
            moved.append(rel_path)
        else:
            shutil.copy2(state.path, dest)
            copied.append(rel_path)

    manifest = {
        "created_at": utc_now(),
        "packs_root": str(packs_root),
        "review_root": str(run_root),
        "move_files": bool(move_files),
        "copied_files": copied,
        "moved_files": moved,
        "missing_files": missing,
        "conflict_records": [c.to_dict() for c in conflict_records],
    }
    run_root.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "review_root": str(run_root),
        "manifest_path": str(manifest_path),
        "copied_files": copied,
        "moved_files": moved,
        "missing_files": missing,
        "conflict_count": len(conflict_records),
    }


def filter_conflicted_actions(plan: SyncPlan) -> SyncPlan:
    filtered = SyncPlan(mode=plan.mode)
    filtered.conflicts = list(plan.conflicts)
    filtered.conflict_records = list(plan.conflict_records)
    filtered.conflicted_rel_paths = set(plan.conflicted_rel_paths)
    filtered.warnings = list(plan.warnings)
    filtered.actions = [
        action
        for action in plan.actions
        if action.source_rel_path == "<db-only>" or action.source_rel_path not in plan.conflicted_rel_paths
    ]
    return filtered
# -----------------------------
# DB access
# -----------------------------


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
            entries_json TEXT NOT NULL,
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



def load_db_records(db_path: Path) -> Dict[str, JsonDict]:
    if not db_path.exists():
        return {}
    conn = sqlite3.connect(str(db_path))
    try:
        init_db(conn)
        rows = conn.execute(
            "SELECT cat_id, category, meta_json, pack_paths_json, entry_keys_json, entries_json, updated_at FROM category_meta"
        ).fetchall()
    finally:
        conn.close()

    out: Dict[str, JsonDict] = {}
    for cat_id, category, meta_json, pack_paths_json, entry_keys_json, entries_json, updated_at in rows:
        meta = json.loads(meta_json) if meta_json else {}
        if not isinstance(meta, dict):
            meta = {}
        out[str(cat_id)] = {
            "cat_id": str(cat_id),
            "category": normalize_category(str(category)),
            "meta": meta,
            "pack_paths": json.loads(pack_paths_json) if pack_paths_json else [],
            "entry_keys": json.loads(entry_keys_json) if entry_keys_json else [],
            "entries": json.loads(entries_json) if entries_json else {},
            "updated_at": updated_at,
        }
    return out



def load_schema_fields(db_path: Path) -> List[str]:
    if not db_path.exists():
        return list(DEFAULT_META_SCHEMA)
    conn = sqlite3.connect(str(db_path))
    try:
        init_db(conn)
        row = conn.execute(
            "SELECT schema_json FROM meta_schema WHERE schema_key = ?",
            ("category_meta_fields",),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return list(DEFAULT_META_SCHEMA)
    try:
        fields = json.loads(row[0])
    except Exception:
        return list(DEFAULT_META_SCHEMA)
    if not isinstance(fields, list):
        return list(DEFAULT_META_SCHEMA)
    cleaned = [str(x).strip() for x in fields if str(x).strip()]
    merged = list(dict.fromkeys(list(DEFAULT_META_SCHEMA) + cleaned))
    return merged



def write_schema(conn: sqlite3.Connection, schema_fields: Sequence[str]) -> None:
    conn.execute(
        "REPLACE INTO meta_schema(schema_key, schema_json, updated_at) VALUES (?, ?, ?)",
        ("category_meta_fields", json.dumps(list(schema_fields), ensure_ascii=False), utc_now()),
    )



def upsert_db_record(
    conn: sqlite3.Connection,
    *,
    cat_id: str,
    category: str,
    meta: JsonDict,
    schema_fields: Sequence[str],
    pack_paths: Sequence[str],
    entry_keys: Sequence[str],
    entries: JsonDict,
) -> None:
    conn.execute("""
    REPLACE INTO category_meta(
        cat_id, category, meta_json, meta_fields_json,
        pack_paths_json, entry_keys_json, entries_json, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        cat_id,
        category,
        json.dumps(meta, ensure_ascii=False),
        json.dumps(schema_fields, ensure_ascii=False),
        json.dumps(pack_paths, ensure_ascii=False),
        json.dumps(sorted(set(entry_keys)), ensure_ascii=False),
        json.dumps(entries, ensure_ascii=False),
        utc_now()
    ))


# -----------------------------
# Scanning and planning
# -----------------------------


def collect_schema_fields_from_json(packs_root: Path) -> List[str]:
    fields = list(DEFAULT_META_SCHEMA)
    seen = set(fields)
    for path in iter_json_files(packs_root):
        try:
            data = read_json(path)
        except Exception:
            continue
        meta = data.get("_meta") if isinstance(data, dict) and isinstance(data.get("_meta"), dict) else {}
        for key in meta.keys():
            key = str(key).strip()
            if key and key not in seen:
                seen.add(key)
                fields.append(key)
    return fields



def scan_pack_states(packs_root: Path, db_path: Path, schema_fields: Sequence[str]) -> List[PackState]:
    db_records = load_db_records(db_path)
    db_by_cat_id = {cid: rec for cid, rec in db_records.items()}
    existing_ids = set(db_by_cat_id)
    states: List[PackState] = []

    for path in iter_json_files(packs_root):
        data = read_json(path)
        if not isinstance(data, dict):
            continue
        rel_path = path.resolve().relative_to(packs_root.resolve()).as_posix()
        meta = data.get("_meta") if isinstance(data.get("_meta"), dict) else {}
        file_category = normalize_category(str(meta.get("category") or ""))
        path_category = derive_category_from_path(packs_root, path)
        cat_id = str(meta.get("cat_id") or "").strip()
        db_row = db_by_cat_id.get(cat_id) if cat_id else None
        exists_in_db = db_row is not None
        is_new_to_db = not exists_in_db

        if not cat_id:
            cat_id = gen_cat_id(existing_ids)
        else:
            existing_ids.add(cat_id)

        if db_row is None:
            db_category = None
        else:
            db_category = normalize_category(str(db_row["category"]))

        entry_keys = sorted(k for k in data.keys() if isinstance(k, str) and not k.startswith("_"))
        states.append(
            PackState(
                path=path,
                rel_path=rel_path,
                data=data,
                meta=dict(meta),
                entry_keys=entry_keys,
                cat_id=cat_id,
                file_category=file_category,
                path_category=path_category,
                db_category=db_category,
                exists_in_db=exists_in_db,
                is_new_to_db=is_new_to_db,
            )
        )
    return states



def decide_category(
    state: PackState,
    *,
    trust_db: bool,
    strict_category_conflicts: bool,
) -> Tuple[str, str, List[str], Optional[str]]:
    warnings: List[str] = []
    conflict: Optional[str] = None

    file_cat = state.file_category
    path_cat = state.path_category
    db_cat = state.db_category

    if state.is_new_to_db:
        if file_cat:
            category = file_cat
            resolution = "new_file:file_category"
        elif path_cat:
            category = path_cat
            resolution = "new_file:path_category"
            warnings.append("Missing _meta.category; path-derived category used")
        else:
            category = "unresolved"
            resolution = "new_file:unresolved"
            conflict = f"{state.rel_path}: could not resolve category"
        return category, resolution, warnings, conflict

    if trust_db:
        if db_cat:
            category = db_cat
            resolution = "db_wins"
            if file_cat and file_cat != db_cat:
                warnings.append(f"File category differs from DB; DB wins ({file_cat} -> {db_cat})")
            return category, resolution, warnings, None

    # Default: file wins for existing items when provided.
    if file_cat:
        category = file_cat
        resolution = "file_wins"
        if db_cat and file_cat != db_cat:
            warnings.append(f"DB category differs; file wins ({db_cat} -> {file_cat})")
            if strict_category_conflicts:
                conflict = f"{state.rel_path}: category conflict db='{db_cat}' file='{file_cat}'"
        return category, resolution, warnings, conflict

    if db_cat:
        category = db_cat
        resolution = "db_repairs_missing_file_category"
        warnings.append("Missing _meta.category; repaired from DB")
        return category, resolution, warnings, None

    if path_cat:
        category = path_cat
        resolution = "path_fallback"
        warnings.append("Missing file and DB category; path-derived category used")
        return category, resolution, warnings, None

    category = "unresolved"
    resolution = "unresolved"
    conflict = f"{state.rel_path}: could not resolve category"
    return category, resolution, warnings, conflict



def build_json_plan(
    *,
    packs_root: Path,
    db_path: Path,
    mode: str,
    trust_db: bool,
    strict_category_conflicts: bool,
) -> Tuple[SyncPlan, List[PackState], List[str]]:
    schema_fields = list(dict.fromkeys(load_schema_fields(db_path) + collect_schema_fields_from_json(packs_root)))
    states = scan_pack_states(packs_root, db_path, schema_fields)
    db_records = load_db_records(db_path)
    plan = SyncPlan(mode=mode)

    seen_cat_ids: Dict[str, str] = {}
    seen_categories: Dict[str, str] = {}

    for state in states:
        category, resolution, warnings, conflict = decide_category(
            state, trust_db=trust_db, strict_category_conflicts=strict_category_conflicts
        )
        if category == "unresolved":
            if conflict:
                plan.add_conflict(
                    conflict,
                    source_rel_paths=[state.rel_path],
                    category=None,
                    cat_id=state.cat_id or None,
                )
            continue

        temp_meta = dict(state.meta)
        temp_meta["cat_id"] = state.cat_id
        temp_meta["category"] = category
        shaped, added = ensure_meta_shape(temp_meta, state.rel_path, schema_fields)

        dest_rel = category_to_relpath(category, state.cat_id)
        db_action = "insert" if not state.exists_in_db else ("update" if state.db_category != category or added or shaped != state.meta else "update")
        json_action = "update" if state.rel_path != dest_rel or added or state.meta.get("cat_id") != state.cat_id or state.meta.get("category") != category else "skip"
        move_required = state.rel_path != dest_rel

        if state.cat_id in seen_cat_ids and seen_cat_ids[state.cat_id] != category:
            other_category = seen_cat_ids[state.cat_id]
            other_rel = next((a.source_rel_path for a in plan.actions if a.cat_id == state.cat_id), None)
            plan.add_conflict(
                f"cat_id collision: {state.cat_id} maps to both '{other_category}' and '{category}'",
                source_rel_paths=[p for p in [other_rel, state.rel_path] if p],
                category=category,
                cat_id=state.cat_id,
                extra={"existing_category": other_category, "incoming_category": category},
            )
        else:
            seen_cat_ids[state.cat_id] = category
        if category in seen_categories and seen_categories[category] != state.cat_id:
            other_cat_id = seen_categories[category]
            other_rel = next((a.source_rel_path for a in plan.actions if a.category == category), None)
            plan.add_conflict(
                f"category collision: {category} maps to both '{other_cat_id}' and '{state.cat_id}'",
                source_rel_paths=[p for p in [other_rel, state.rel_path] if p],
                category=category,
                cat_id=state.cat_id,
                extra={"existing_cat_id": other_cat_id, "incoming_cat_id": state.cat_id},
            )
        else:
            seen_categories[category] = state.cat_id

        if state.exists_in_db and state.db_category and state.db_category != category and resolution == "file_wins":
            plan.warnings.append(f"{state.rel_path}: file category overrides DB ({state.db_category} -> {category})")

        if conflict:
            plan.add_conflict(
                conflict,
                source_rel_paths=[state.rel_path],
                category=category,
                cat_id=state.cat_id,
            )

        action = PlannedAction(
            source_rel_path=state.rel_path,
            category=category,
            cat_id=state.cat_id,
            dest_rel_path=dest_rel,
            resolution=resolution,
            db_action=db_action,
            json_action=json_action,
            move_required=move_required,
            missing_fields_added=added,
            warnings=warnings,
        )
        plan.actions.append(action)

    # Check for DB records not represented by files.
    file_cat_ids = {s.cat_id for s in states}
    for cat_id, row in sorted(db_records.items()):
        if cat_id not in file_cat_ids and mode in {"audit", "sync-db-to-json"}:
            rel = category_to_relpath(row["category"], cat_id)
            plan.actions.append(
                PlannedAction(
                    source_rel_path="<db-only>",
                    category=row["category"],
                    cat_id=cat_id,
                    dest_rel_path=rel,
                    resolution="db_only_record",
                    db_action="keep",
                    json_action="write" if mode == "sync-db-to-json" else "skip",
                    move_required=False,
                    missing_fields_added=[],
                    warnings=["Record exists only in DB"],
                )
            )

    return plan, states, schema_fields


# -----------------------------
# Apply modes
# -----------------------------


def apply_intake_or_json_to_db(
    *,
    packs_root: Path,
    db_path: Path,
    plan: SyncPlan,
    states: List[PackState],
    schema_fields: Sequence[str],
    dry_run: bool,
    make_backups: bool,
) -> JsonDict:
    state_map = {s.rel_path: s for s in states}
    backup_root = packs_root.parent / "backups" / "pack_catalog_sync"
    written_json = 0
    moved_json = 0
    db_written = 0

    if not dry_run:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        init_db(conn)
        write_schema(conn, schema_fields)
    else:
        conn = None

    try:
        for action in plan.actions:
            if action.source_rel_path == "<db-only>":
                continue
            state = state_map[action.source_rel_path]
            data = dict(state.data)
            meta = dict(state.meta)
            meta["cat_id"] = action.cat_id
            meta["category"] = action.category
            shaped, _ = ensure_meta_shape(meta, action.dest_rel_path, schema_fields)
            data["_meta"] = shaped
            dest_path = packs_root / action.dest_rel_path
            pack_paths = [action.dest_rel_path]

            if not dry_run:
                if make_backups:
                    backup_copy(state.path, backup_root)
                write_json(dest_path, data)
                written_json += 1
                if dest_path.resolve() != state.path.resolve():
                    moved_json += 1
                    if state.path.exists():
                        state.path.unlink(missing_ok=True)
                        remove_empty_dirs(state.path.parent, packs_root)
                entries = {
                    k: v for k, v in data.items()
                    if isinstance(k, str) and not k.startswith("_")
                }
                upsert_db_record(
                    conn,
                    cat_id=state.cat_id,
                    category=action.category,
                    meta=shaped,
                    schema_fields=schema_fields,
                    pack_paths=pack_paths,
                    entry_keys=state.entry_keys,
                    entries=entries,
                )
                db_written += 1

        if conn is not None:
            conn.commit()
    finally:
        if conn is not None:
            conn.close()

    return {
        "mode": plan.mode,
        "dry_run": dry_run,
        "backup_root": str(backup_root),
        "json_written": written_json,
        "json_moved": moved_json,
        "db_rows_written": db_written,
        "plan": plan.to_report(),
    }



def apply_db_to_json(
    *,
    packs_root: Path,
    db_path: Path,
    plan: SyncPlan,
    states: List[PackState],
    schema_fields: Sequence[str],
    dry_run: bool,
    make_backups: bool,
    cleanup_old: bool,
) -> JsonDict:
    db_records = load_db_records(db_path)
    states_by_cat_id: Dict[str, List[PackState]] = {}
    for state in states:
        states_by_cat_id.setdefault(state.cat_id, []).append(state)

    backup_root = packs_root.parent / "backups" / "pack_catalog_sync"
    written_json = 0
    removed_json = 0

    for action in plan.actions:
        if action.json_action == "skip":
            continue
        dest_path = packs_root / action.dest_rel_path
        db_row = db_records.get(action.cat_id)
        source_group = states_by_cat_id.get(action.cat_id, [])

        if db_row is None:
            continue

        base_meta = dict(db_row["meta"] or {})
        base_meta["cat_id"] = action.cat_id
        base_meta["category"] = action.category
        shaped, _ = ensure_meta_shape(base_meta, action.dest_rel_path, schema_fields)
        merged: JsonDict = {"_meta": shaped}
        db_entries = db_row.get("entries") or {}
        for key, value in db_entries.items():
            if isinstance(key, str) and not key.startswith("_"):
                merged[key] = value

        for state in sorted(source_group, key=lambda s: s.rel_path):
            for key, value in state.data.items():
                if isinstance(key, str) and not key.startswith("_"):
                    merged[key] = value

        if not dry_run:
            for state in source_group:
                if make_backups and state.path.exists():
                    backup_copy(state.path, backup_root)
            write_json(dest_path, merged)
            written_json += 1

            if cleanup_old:
                for state in source_group:
                    if state.path.resolve() != dest_path.resolve() and state.path.exists():
                        state.path.unlink(missing_ok=True)
                        removed_json += 1
                        remove_empty_dirs(state.path.parent, packs_root)

    return {
        "mode": plan.mode,
        "dry_run": dry_run,
        "backup_root": str(backup_root),
        "json_written": written_json,
        "json_removed": removed_json,
        "plan": plan.to_report(),
    }


# -----------------------------
# Console presentation
# -----------------------------


def print_human_plan(plan: SyncPlan, limit: int = 50) -> None:
    summary = plan.summary()
    print("=" * 78)
    print(f"Mode: {summary['mode']}")
    print(
        f"Items: {summary['items']} | DB inserts: {summary['db_inserts']} | DB updates: {summary['db_updates']} | "
        f"JSON updates: {summary['json_updates']} | Moves: {summary['moves']} | Conflicts: {summary['conflicts']}"
    )
    print("=" * 78)

    if plan.conflicts:
        print("Conflicts:")
        for msg in plan.conflicts[:20]:
            print(f"  - {msg}")
        if len(plan.conflicts) > 20:
            print(f"  ... {len(plan.conflicts) - 20} more")
        print("-" * 78)

    shown = 0
    for action in plan.actions:
        print(f"Source: {action.source_rel_path}")
        print(f"  Category:   {action.category}")
        print(f"  Cat ID:     {action.cat_id}")
        print(f"  Resolution: {action.resolution}")
        print(f"  Dest:       {action.dest_rel_path}")
        print(f"  DB action:  {action.db_action}")
        print(f"  JSON:       {action.json_action}")
        if action.missing_fields_added:
            print(f"  Added:      {', '.join(action.missing_fields_added)}")
        for warn in action.warnings:
            print(f"  Warning:    {warn}")
        print("-" * 78)
        shown += 1
        if shown >= limit and len(plan.actions) > limit:
            print(f"... truncated {len(plan.actions) - limit} additional actions")
            break


# -----------------------------
# CLI
# -----------------------------


def make_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Standalone dev tool for pack intake, JSON<->DB sync, and category-aware file placement."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--packs-root", required=True, help="Root folder containing pack JSON files")
        p.add_argument("--db", required=True, help="Path to category_meta.sqlite")
        p.add_argument("--report-json", default=None, help="Optional path to write a full JSON report")
        p.add_argument("--strict-category-conflicts", action="store_true", help="Report category conflicts as conflicts instead of only warnings")
        p.add_argument("--trust-db", action="store_true", help="Let DB category win when file and DB disagree")
        p.add_argument("--limit", type=int, default=50, help="Max actions to show in the console preview")

    for name in ["audit", "intake", "sync-json-to-db", "sync-db-to-json"]:
        p = sub.add_parser(name)
        add_common(p)
        if name != "audit":
            p.add_argument("--apply", action="store_true", help="Actually write changes; otherwise preview only")
            p.add_argument("--backup", action="store_true", help="Create timestamped backups before file writes")
            p.add_argument(
                "--abort-on-conflicts",
                action="store_true",
                help="Stop the run if conflicts are detected instead of isolating and continuing",
            )
        if name == "sync-db-to-json":
            p.add_argument("--no-cleanup-old", action="store_true", help="Keep older source files in place when writing canonical files")
       

    return ap



def write_report(path: Optional[str], report: JsonDict) -> None:
    if not path:
        return
    out = Path(path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")



def main() -> None:
    args = make_parser().parse_args()
    packs_root = Path(args.packs_root).expanduser().resolve()
    db_path = Path(args.db).expanduser().resolve()

    if not packs_root.exists() or not packs_root.is_dir():
        raise SystemExit(f"Invalid --packs-root: {packs_root}")

    effective_trust_db = bool(args.trust_db) or args.command == "sync-db-to-json"

    plan, states, schema_fields = build_json_plan(
        packs_root=packs_root,
        db_path=db_path,
        mode=args.command,
        trust_db=effective_trust_db,
        strict_category_conflicts=bool(args.strict_category_conflicts),
    )

    print_human_plan(plan, limit=int(args.limit))

    if args.command == "audit" or not getattr(args, "apply", False):
        report = {
            "applied": False,
            "plan": plan.to_report(),
            "schema_fields": list(schema_fields),
        }
        write_report(args.report_json, report)
        print(json.dumps({"applied": False, **plan.summary()}, ensure_ascii=False, indent=2))
        return

    conflict_review = None
    effective_plan = plan

    if plan.conflicts and bool(getattr(args, "abort_on_conflicts", False)):
        summary = {
            "applied": False,
            "reason": "conflicts_detected",
            "conflict_count": len(plan.conflicts),
            "conflicted_file_count": len(plan.conflicted_rel_paths),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        write_report(
            args.report_json,
            {
                "applied": False,
                "plan": plan.to_report(),
                "schema_fields": list(schema_fields),
            },
        )
        return

    if plan.conflicts:
        conflict_review = isolate_conflicted_files(
            packs_root=packs_root,
            states=states,
            conflict_records=plan.conflict_records,
            move_files=False,
        )
        effective_plan = filter_conflicted_actions(plan)

        if not effective_plan.actions:
            summary = {
                "applied": False,
                "reason": "conflicts_only",
                "conflict_count": len(plan.conflicts),
                "conflicted_file_count": len(plan.conflicted_rel_paths),
                "conflict_review": conflict_review,
            }
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            write_report(
                args.report_json,
                {
                    "applied": False,
                    "plan": plan.to_report(),
                    "effective_plan": effective_plan.to_report(),
                    "schema_fields": list(schema_fields),
                    "conflict_review": conflict_review,
                },
            )
            return

    if args.command in {"intake", "sync-json-to-db"}:
        result = apply_intake_or_json_to_db(
            packs_root=packs_root,
            db_path=db_path,
            plan=effective_plan,
            states=states,
            schema_fields=schema_fields,
            dry_run=False,
            make_backups=bool(args.backup),
        )
    elif args.command == "sync-db-to-json":
        result = apply_db_to_json(
            packs_root=packs_root,
            db_path=db_path,
            plan=effective_plan,
            states=states,
            schema_fields=schema_fields,
            dry_run=False,
            make_backups=bool(args.backup),
            cleanup_old=not bool(args.no_cleanup_old),
        )
    else:
        raise SystemExit(f"Unknown command: {args.command}")

    if conflict_review is not None:
        result["conflict_review"] = conflict_review
        result["full_plan"] = plan.to_report()
        result["partial_apply"] = True
    else:
        result["partial_apply"] = False
    write_report(args.report_json, result)
    summary = result["plan"]["summary"]
    summary = {"applied": True, **summary, **{k: v for k, v in result.items() if k != "plan"}}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
