from __future__ import annotations

import argparse
import json
import re
import zlib
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

JsonDict = Dict[str, Any]

# Optional manual remaps for packs whose canonical category should differ from the
# path-derived default. Keys can be either the relative file path (preferred) or
# the existing/derived category string.
CATEGORY_OVERRIDES: Dict[str, str] = {
    # Example:
    # "clothing/clothing_closure.json": "clothing.modifiers.closure",
    # "clothing_closure": "clothing.modifiers.closure",
}


@dataclass
class FileChange:
    path: str
    old_category: Optional[str]
    new_category: str
    old_title: Optional[str]
    new_title: str
    old_generator_family: Optional[str]
    new_generator_family: Optional[str]
    old_generator_slot: Optional[str]
    new_generator_slot: Optional[str]
    old_generatable: Any
    new_generatable: bool
    old_parents: Any
    new_parents: Optional[List[str]]
    old_meta_key: Any
    new_meta_key: Optional[int]
    changed_fields: List[str]


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

    # Strip an exact repeated folder prefix: pants_length inside .../pants/ -> length
    if last_folder:
        if stem == last_folder:
            stem = ""
        elif stem.startswith(last_folder + "_"):
            stem = stem[len(last_folder) + 1 :]
        elif stem.startswith(last_folder + "."):
            stem = stem[len(last_folder) + 1 :]

    return [p for p in stem.replace("_", ".").split(".") if p]


def derive_category(packs_root: Path, file_path: Path, overrides: Dict[str, str] | None = None) -> str:
    overrides = overrides or {}
    rel = file_path.resolve().relative_to(packs_root.resolve())
    rel_key = rel.as_posix()
    stem_key = _norm_segment(file_path.stem)

    # Allow precise manual remaps for edge cases like clothing_closure -> clothing.modifiers.closure
    if rel_key in overrides:
        return _norm_segment(overrides[rel_key])
    if stem_key in overrides:
        return _norm_segment(overrides[stem_key])

    folder_parts = _path_parts_under_root(packs_root, file_path)
    last_folder = folder_parts[-1] if folder_parts else ""
    leaf_parts = _normalize_leaf_stem(file_path.stem, last_folder)

    parts = folder_parts + leaf_parts
    cat = ".".join([p for p in parts if p])

    # Secondary override by derived category if useful.
    if cat in overrides:
        return _norm_segment(overrides[cat])
    return cat


def title_from_category(category: str) -> str:
    parts = _split_dot(category)
    if not parts:
        return category
    title_parts = parts[-2:] if len(parts) >= 2 else parts[-1:]
    words: List[str] = []
    for part in title_parts:
        for w in part.replace("-", "_").split("_"):
            w = w.strip()
            if w:
                words.append(w.capitalize())
    return " ".join(words) if words else category


def generator_fields_from_category(category: str) -> tuple[Optional[str], Optional[str]]:
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


def stable_meta_key(category: str) -> int:
    # Stable, deterministic 6-digit-ish positive integer from canonical category.
    return zlib.crc32(category.encode("utf-8")) % 900000 + 100000


def transform_pack(
    packs_root: Path,
    file_path: Path,
    *,
    overrides: Dict[str, str] | None = None,
    set_meta_key: bool = False,
) -> tuple[JsonDict, FileChange] | tuple[None, None]:
    data = _read_json(file_path)
    if not isinstance(data, dict):
        raise ValueError("Top-level JSON must be an object/dict")

    meta = data.get("_meta")
    if not isinstance(meta, dict):
        meta = {}

    old_meta = dict(meta)
    old_category = old_meta.get("category")
    old_title = old_meta.get("title")
    old_family = old_meta.get("generator_family")
    old_slot = old_meta.get("generator_slot")
    old_generatable = old_meta.get("generatable")
    old_parents = old_meta.get("parents")
    old_meta_key = old_meta.get("meta_key")

    category = derive_category(packs_root, file_path, overrides=overrides)
    title = title_from_category(category)
    generator_family, generator_slot = generator_fields_from_category(category)

    meta["category"] = category
    meta["title"] = title
    if generator_family:
        meta["generator_family"] = generator_family
    else:
        meta.pop("generator_family", None)
    if generator_slot:
        meta["generator_slot"] = generator_slot
    else:
        meta.pop("generator_slot", None)
    meta["generatable"] = True

    # Preserve useful explicit fields, but normalize where sensible.
    related = normalize_list_str(meta.get("related_categories"))
    if related:
        meta["related_categories"] = related
    elif "related_categories" in meta:
        meta.pop("related_categories", None)

    aliases = normalize_list_str(meta.get("aliases"))
    if aliases:
        meta["aliases"] = aliases
    elif "aliases" in meta:
        meta.pop("aliases", None)

    # parents is redundant when it matches generator_family/immediate dot parent; keep only if different.
    parents = normalize_list_str(meta.get("parents"))
    if generator_family:
        filtered = [p for p in parents if p.strip().lower() != generator_family.lower()]
    else:
        filtered = parents
    if filtered:
        meta["parents"] = filtered
        new_parents: Optional[List[str]] = filtered
    else:
        meta.pop("parents", None)
        new_parents = None

    if set_meta_key:
        meta["meta_key"] = stable_meta_key(category)
    else:
        meta.pop("meta_key", None) if ("meta_key" in meta and old_meta_key is None) else None

    data["_meta"] = meta

    changed_fields: List[str] = []
    for field in [
        "category",
        "title",
        "generator_family",
        "generator_slot",
        "generatable",
        "parents",
        "related_categories",
        "aliases",
        "meta_key",
    ]:
        if old_meta.get(field) != meta.get(field):
            changed_fields.append(field)

    if not changed_fields:
        return None, None

    change = FileChange(
        path=str(file_path),
        old_category=old_category if isinstance(old_category, str) else None,
        new_category=category,
        old_title=old_title if isinstance(old_title, str) else None,
        new_title=title,
        old_generator_family=old_family if isinstance(old_family, str) else None,
        new_generator_family=generator_family,
        old_generator_slot=old_slot if isinstance(old_slot, str) else None,
        new_generator_slot=generator_slot,
        old_generatable=old_generatable,
        new_generatable=True,
        old_parents=old_parents,
        new_parents=new_parents,
        old_meta_key=old_meta_key,
        new_meta_key=meta.get("meta_key") if set_meta_key else None,
        changed_fields=changed_fields,
    )
    return data, change


def normalize_packs(
    packs_root: Path,
    *,
    apply: bool = False,
    make_backups: bool = True,
    overrides: Dict[str, str] | None = None,
    set_meta_key: bool = False,
) -> Dict[str, Any]:
    packs_root = packs_root.resolve()
    files = sorted([p for p in packs_root.rglob("*.json") if p.is_file()])

    changed: List[FileChange] = []
    errors: List[Dict[str, str]] = []
    backups: List[str] = []

    for fp in files:
        try:
            new_data, change = transform_pack(
                packs_root,
                fp,
                overrides=overrides,
                set_meta_key=set_meta_key,
            )
            if change is None:
                continue
            changed.append(change)
            if apply and new_data is not None:
                if make_backups:
                    backups.append(str(_backup(fp)))
                _write_json(fp, new_data)
        except Exception as e:
            errors.append({"file": str(fp), "error": repr(e)})

    return {
        "packs_root": str(packs_root),
        "apply": apply,
        "make_backups": make_backups,
        "set_meta_key": set_meta_key,
        "override_count": len(overrides or {}),
        "counts": {
            "total_files": len(files),
            "changed": len(changed),
            "errors": len(errors),
        },
        "changed": [asdict(c) for c in changed],
        "backups": backups,
        "errors": errors,
    }


def _load_overrides(path: Optional[Path]) -> Dict[str, str]:
    merged = dict(CATEGORY_OVERRIDES)
    if not path:
        return merged
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Overrides file must be a JSON object mapping file/category -> category")
    for k, v in data.items():
        if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
            merged[k.strip()] = v.strip()
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize pack metadata for modular/generatable packs. "
            "Derives category from folder path + filename, strips repeated folder prefixes, "
            "converts to dot notation, creates titles from the last two category pieces, "
            "sets generator_family/generator_slot/generatable, and removes redundant parents."
        )
    )
    parser.add_argument("packs_root", type=Path, help="Root folder containing pack JSON files")
    parser.add_argument("--apply", action="store_true", help="Write changes to disk")
    parser.add_argument("--no-backups", action="store_true", help="Do not create .bak timestamp backups")
    parser.add_argument(
        "--overrides-file",
        type=Path,
        help="Optional JSON file mapping relative file path or old category -> desired category",
    )
    parser.add_argument(
        "--set-meta-key",
        action="store_true",
        help="Also write a stable auto-generated meta_key derived from the canonical category",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Optional path to write the JSON report. Defaults to <packs_root>/normalize_generatable_report.json",
    )
    args = parser.parse_args()

    overrides = _load_overrides(args.overrides_file)
    report = normalize_packs(
        args.packs_root,
        apply=args.apply,
        make_backups=not args.no_backups,
        overrides=overrides,
        set_meta_key=args.set_meta_key,
    )

    out_path = args.out or (args.packs_root.resolve() / "normalize_generatable_report.json")
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote report: {out_path}")
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
