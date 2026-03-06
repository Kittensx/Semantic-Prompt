import json
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


def _read_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _as_list(x) -> List[str]:
    if not x:
        return []
    if isinstance(x, str):
        x = [x]
    if not isinstance(x, list):
        return []
    out = []
    for v in x:
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
    return out


def _infer_dot_parent(cat: str) -> str | None:
    # "appearance.skin.quality" -> "appearance.skin"
    if not cat or "." not in cat:
        return None
    parent = cat.rsplit(".", 1)[0].strip()
    return parent or None


def generate_category_index(
    packs_dir: Path,
    out_file: Path,
    *,
    infer_dot_parents_if_missing: bool = True,
    include_only_categories_with_pack_files: bool = True,
) -> Dict[str, Any]:
    """
    Builds categories.index.json from pack _meta blocks.

    - parents/related/aliases come from _meta
    - children is auto-derived
    - titles: _meta.title or fallback to category id
    """

    cats: Dict[str, Dict[str, Any]] = {}

    def ensure_cat(cat_id: str) -> Dict[str, Any]:
        cat_id = (cat_id or "").strip()
        if not cat_id:
            return {}
        if cat_id not in cats:
            cats[cat_id] = {
                "title": cat_id,
                "parents": [],
                "children": [],
                "related_categories": [],
                "aliases": [],
            }
        return cats[cat_id]

    # --- Pass 1: scan packs ---
    pack_categories: Set[str] = set()

    for fp in packs_dir.rglob("*.json"):
        try:
            data = _read_json(fp)
        except Exception:
            continue

        meta = data.get("_meta") or {}
        category = meta.get("category")
        if not isinstance(category, str) or not category.strip():
            continue

        category = category.strip()
        pack_categories.add(category)

        node = ensure_cat(category)

        title = meta.get("title")
        if isinstance(title, str) and title.strip():
            node["title"] = title.strip()

        parents = _as_list(meta.get("parents"))
        related = _as_list(meta.get("related_categories"))
        aliases = _as_list(meta.get("aliases"))

        # Optional: infer dot parent if parents missing
        if infer_dot_parents_if_missing and not parents:
            inferred = _infer_dot_parent(category)
            if inferred:
                parents = [inferred]

        # Merge into node (dedupe later)
        node["parents"].extend(parents)
        node["related_categories"].extend(related)
        node["aliases"].extend(aliases)

        # Also ensure any referenced categories exist as nodes
        for p in parents:
            ensure_cat(p)
        for r in related:
            ensure_cat(r)

    # Optionally drop categories that have no pack file
    if include_only_categories_with_pack_files:
        # Keep referenced nodes too (parents/related) so the graph stays connected.
        referenced: Set[str] = set()
        for cid, node in cats.items():
            for p in node["parents"]:
                referenced.add(p)
            for r in node["related_categories"]:
                referenced.add(r)
        keep = pack_categories | referenced
        cats = {k: v for k, v in cats.items() if k in keep}

    # --- Pass 2: derive children from parents ---
    children_map: Dict[str, Set[str]] = {}
    for cid, node in cats.items():
        for p in node.get("parents", []) or []:
            if not p:
                continue
            children_map.setdefault(p, set()).add(cid)

    for parent, kids in children_map.items():
        ensure_cat(parent)
        cats[parent]["children"].extend(sorted(kids))

    # --- Pass 3: dedupe + sort lists ---
    def dedupe_sort(lst: List[str]) -> List[str]:
        seen = set()
        out = []
        for x in lst:
            x = (x or "").strip()
            if not x:
                continue
            xl = x.lower()
            if xl in seen:
                continue
            seen.add(xl)
            out.append(x)
        return sorted(out)

    for cid, node in cats.items():
        node["parents"] = dedupe_sort(node.get("parents", []))
        node["children"] = dedupe_sort(node.get("children", []))
        node["related_categories"] = dedupe_sort(node.get("related_categories", []))
        node["aliases"] = dedupe_sort(node.get("aliases", []))

        # Fallback title if still empty
        if not node.get("title"):
            node["title"] = cid

    out = {
        "_meta": {
            "version": "1.0",
            "generated_from": str(packs_dir),
        }
    }
    # Stable output ordering
    for cid in sorted(cats.keys()):
        out[cid] = cats[cid]

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    # Adjust these paths to match your extension layout.
    # Your packs live at: extension_root/semantic/packs  :contentReference[oaicite:1]{index=1}
    here = Path(__file__).resolve()
    ext_root = here.parents[1]  # tools/ -> extension root (adjust if needed)

    packs_dir = ext_root / "semantic" / "packs"
    out_file = ext_root / "semantic" / "categories.index.json"

    generate_category_index(
        packs_dir=packs_dir,
        out_file=out_file,
        infer_dot_parents_if_missing=True,
        include_only_categories_with_pack_files=True,
    )

    print(f"Wrote: {out_file}")