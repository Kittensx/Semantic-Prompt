import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Tuple


def _read_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _backup(path: Path) -> Path:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    bak = path.with_suffix(path.suffix + f".bak_{ts}")
    if path.exists():
        bak.write_bytes(path.read_bytes())
    return bak


def _norm_list(x) -> List[str]:
    if not x:
        return []
    if isinstance(x, str):
        x = [x]
    if not isinstance(x, list):
        return []
    out = []
    for v in x:
        if isinstance(v, str):
            s = v.strip()
            if s:
                out.append(s)
    return out


def _dedupe_sorted(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        x = (x or "").strip()
        if not x:
            continue
        xl = x.lower()
        if xl in seen:
            continue
        seen.add(xl)
        out.append(x)
    return sorted(out)


def _titleize(cat_id: str) -> str:
    # "appearance.physical.skin.skin_surface" -> "Skin Surface"
    last = (cat_id or "").split(".")[-1]
    parts = last.replace("-", "_").split("_")
    parts = [p.capitalize() for p in parts if p]
    return " ".join(parts) if parts else cat_id


def _path_to_dot(rel_dir: Path) -> str:
    # appearance/physical/skin -> appearance.physical.skin
    parts = [p for p in rel_dir.parts if p and p not in (".", "..")]
    return ".".join(parts)


def _compute_category(
    packs_root: Path,
    file_path: Path,
    *,
    include_filename_as_leaf: bool = True,
) -> str:
    rel = file_path.relative_to(packs_root)
    rel_dir = rel.parent
    folder_dot = _path_to_dot(rel_dir)

    stem = file_path.stem.strip()
    if include_filename_as_leaf and stem:
        # appearance.physical.skin + skin_surface -> appearance.physical.skin.skin_surface
        return f"{folder_dot}.{stem}" if folder_dot else stem
    else:
        # folder-only category
        return folder_dot or stem


def _infer_parents(cat_id: str) -> List[str]:
    # immediate parent only
    if "." not in cat_id:
        return []
    return [cat_id.rsplit(".", 1)[0]]


def upgrade_packs(
    packs_root: Path,
    *,
    include_filename_as_leaf: bool = True,
    force: bool = False,
    ensure_children: bool = True,
) -> Dict[str, Any]:
    """
    - Reads every *.json under packs_root recursively (your loader already supports rglob). :contentReference[oaicite:3]{index=3}
    - Writes/updates _meta using folder path + optionally filename.
    - Optionally computes children after scanning all categories.
    """

    packs_root = packs_root.resolve()
    files = sorted(packs_root.rglob("*.json"))

    # First pass: compute category ids for every file
    file_to_cat: Dict[Path, str] = {}
    cat_to_file: Dict[str, Path] = {}
    for fp in files:
        cat = _compute_category(packs_root, fp, include_filename_as_leaf=include_filename_as_leaf)
        file_to_cat[fp] = cat
        # last-one-wins if duplicates; you can change to detect collisions
        cat_to_file[cat] = fp

    # Build parent->children mapping (category graph)
    parent_to_children: Dict[str, List[str]] = {}
    for cat in cat_to_file.keys():
        if "." in cat:
            parent = cat.rsplit(".", 1)[0]
            parent_to_children.setdefault(parent, []).append(cat)

    updated = []
    skipped = []
    errors = []

    for fp in files:
        try:
            data = _read_json(fp)
            meta = data.get("_meta") or {}
            old_meta = dict(meta) if isinstance(meta, dict) else {}
            if not isinstance(meta, dict):
                meta = {}

            cat_id = file_to_cat[fp]

            # "Already upgraded" heuristic:
            # if meta has category AND (parents or title or related_categories) we assume it’s been touched.
            already = bool(meta.get("category")) and any(
                k in meta for k in ("parents", "title", "related_categories", "aliases", "children")
            )
            if already and not force:
                # Still optionally refresh related_categories/children if you want:
                if ensure_children:
                    # If we want children in meta, we may still update it.
                    kids = parent_to_children.get(cat_id, [])
                    new_children = _dedupe_sorted(kids)
                    if new_children and meta.get("children") != new_children:
                        _backup(fp)
                        meta["children"] = new_children
                        data["_meta"] = meta
                        _write_json(fp, data)
                        updated.append(str(fp))
                    else:
                        skipped.append(str(fp))
                else:
                    skipped.append(str(fp))
                continue

            # Write/normalize meta fields
            meta["category"] = cat_id

            # Title: keep existing if present, else derive
            if not (isinstance(meta.get("title"), str) and meta["title"].strip()):
                meta["title"] = _titleize(cat_id)

            # Parents: keep existing list if present, else infer from dots
            parents = _norm_list(meta.get("parents"))
            if not parents:
                parents = _infer_parents(cat_id)
            meta["parents"] = _dedupe_sorted(parents)

            # Related categories: preserve existing, just normalize
            related = _norm_list(meta.get("related_categories"))
            meta["related_categories"] = _dedupe_sorted(related)

            # Aliases: preserve existing, normalize
            aliases = _norm_list(meta.get("aliases"))
            meta["aliases"] = _dedupe_sorted(aliases)

            # Children: compute if requested
            if ensure_children:
                kids = parent_to_children.get(cat_id, [])
                meta["children"] = _dedupe_sorted(kids)

            # Write only if changed
            changed = (old_meta != meta) or (data.get("_meta") != meta)
            if changed:
                _backup(fp)
                data["_meta"] = meta
                _write_json(fp, data)
                updated.append(str(fp))
            else:
                skipped.append(str(fp))

        except Exception as e:
            errors.append({"file": str(fp), "error": repr(e)})

    return {
        "packs_root": str(packs_root),
        "include_filename_as_leaf": include_filename_as_leaf,
        "force": force,
        "ensure_children": ensure_children,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "counts": {
            "total_files": len(files),
            "updated": len(updated),
            "skipped": len(skipped),
            "errors": len(errors),
        },
    }


if __name__ == "__main__":
    # Your packs live under extension_root/semantic/packs :contentReference[oaicite:4]{index=4}
    here = Path(__file__).resolve()
    ext_root = here.parents[1]  # tools/ -> extension root (adjust if needed)
    packs_root = ext_root / "semantic" / "packs"

    report = upgrade_packs(
        packs_root,
        include_filename_as_leaf=True,   # folder + filename => dot category
        force=False,                     # skip already-upgraded packs
        ensure_children=True,            # compute children
    )

    out_report = ext_root / "semantic" / "upgrade_report.json"
    out_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote report: {out_report}")
    print(report["counts"])