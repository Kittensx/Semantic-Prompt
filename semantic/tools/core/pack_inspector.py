from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Reuse ideas from fix_json.py :contentReference[oaicite:6]{index=6}

@dataclass
class PackProblem:
    path: Path
    level: str          # "error" | "warn" | "info"
    message: str
    where: str = ""     # e.g. "_meta.category" or "entry:freckles.tags"
    line: Optional[int] = None
    col: Optional[int] = None
    extra: Optional[str] = None
    suggestion: Optional[str] = None  # UI can show as “Fix suggestion”

def read_text_best_effort(p: Path) -> tuple[str, str]:
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8 (replacement)"

def context_snippet(text: str, line: int, col: int, radius: int = 2) -> str:
    lines = text.splitlines()
    idx = max(0, line - 1)
    start = max(0, idx - radius)
    end = min(len(lines), idx + radius + 1)

    out = []
    width = len(str(end))
    for i in range(start, end):
        prefix = f"{i+1:>{width}} | "
        out.append(prefix + lines[i])
        if i == idx:
            caret_pad = " " * (len(prefix) + max(col - 1, 0))
            out.append(caret_pad + "^")
    return "\n".join(out)

def _is_list_str(x: Any) -> bool:
    return isinstance(x, list) and all(isinstance(i, str) for i in x)

def _clean_list_str(x: Any) -> List[str]:
    if not isinstance(x, list):
        return []
    out = []
    for i in x:
        if isinstance(i, str):
            s = i.strip()
            if s:
                out.append(s)
    return out

ALLOWED_ENTRY_FIELDS = {
    "tags", "negative", "aliases", "requires", "excludes",
    "subject", "medium", "composition", "lighting", "palette", "quality", "style",
    "related",  # if you use per-entry related tags
}

CROSS_LIST_FIELDS = {"subject","medium","composition","lighting","palette","quality","style"}

def inspect_pack_file(path: Path) -> List[PackProblem]:
    problems: List[PackProblem] = []
    text, enc = read_text_best_effort(path)

    # Parse JSON with good errors (pattern from fix_json.py) :contentReference[oaicite:7]{index=7}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        problems.append(PackProblem(
            path=path,
            level="error",
            message=e.msg,
            where="file",
            line=e.lineno,
            col=e.colno,
            extra=f"Encoding used: {enc}\n\n{context_snippet(text, e.lineno, e.colno)}",
            suggestion="Fix JSON syntax (trailing commas, single quotes, comments, etc.).",
        ))
        return problems

    if not isinstance(data, dict):
        problems.append(PackProblem(path, "error", "Top-level JSON must be an object/dict.", where="file"))
        return problems

    meta = data.get("_meta")
    if meta is None:
        problems.append(PackProblem(
            path, "warn",
            "Missing _meta block.",
            where="_meta",
            suggestion='Add "_meta": {"category": "<your_category>"} at the top.'
        ))
        meta = {}
    if not isinstance(meta, dict):
        problems.append(PackProblem(path, "error", "_meta must be an object/dict.", where="_meta"))
        meta = {}

    cat = meta.get("category")
    if not isinstance(cat, str) or not cat.strip():
        problems.append(PackProblem(
            path, "error",
            "Missing or invalid _meta.category (must be non-empty string).",
            where="_meta.category",
            suggestion='Set "_meta": {"category": "appearance.skin.quality"} (example).'
        ))
        cat = ""

    # Optional meta checks
    for list_field in ("parents", "children", "related_categories", "aliases"):
        if list_field in meta and not _is_list_str(meta[list_field]):
            problems.append(PackProblem(
                path, "warn",
                f"_meta.{list_field} should be a list of strings.",
                where=f"_meta.{list_field}",
                suggestion=f'Change {list_field} to ["...","..."]'
            ))

    # Entry checks
    keys = [k for k in data.keys() if isinstance(k, str) and not k.startswith("_")]
    key_lc = {k.lower(): k for k in keys}

    for k in keys:
        v = data.get(k)
        if not isinstance(v, dict):
            problems.append(PackProblem(path, "error", "Entry must be an object/dict.", where=f"entry:{k}"))
            continue

        # unknown fields
        for field in v.keys():
            if field not in ALLOWED_ENTRY_FIELDS:
                problems.append(PackProblem(
                    path, "info",
                    f"Unknown field '{field}' in entry (not used by rewriter).",
                    where=f"entry:{k}.{field}"
                ))

        # tags
        if "tags" in v and not _is_list_str(v["tags"]):
            problems.append(PackProblem(path, "error", "tags must be a list of strings.", where=f"entry:{k}.tags"))
        elif "tags" in v and not _clean_list_str(v["tags"]):
            problems.append(PackProblem(path, "warn", "tags list is empty/blank.", where=f"entry:{k}.tags"))

        # negatives
        if "negative" in v and not _is_list_str(v["negative"]):
            problems.append(PackProblem(path, "error", "negative must be a list of strings.", where=f"entry:{k}.negative"))

        # aliases
        if "aliases" in v:
            if not _is_list_str(v["aliases"]):
                problems.append(PackProblem(path, "error", "aliases must be a list of strings.", where=f"entry:{k}.aliases"))
            else:
                for a in _clean_list_str(v["aliases"]):
                    # collision with real key in same file
                    if a.lower() in key_lc and a.lower() != k.lower():
                        problems.append(PackProblem(
                            path, "warn",
                            f"Alias '{a}' collides with real key '{key_lc[a.lower()]}' in same pack.",
                            where=f"entry:{k}.aliases",
                            suggestion="Remove or rename the alias to avoid ambiguity."
                        ))

        # requires
        if "requires" in v:
            if not _is_list_str(v["requires"]):
                problems.append(PackProblem(path, "error", "requires must be a list of strings.", where=f"entry:{k}.requires"))

        # excludes supports str or list[str] (matches rewriter behavior) :contentReference[oaicite:8]{index=8}
        if "excludes" in v:
            ex = v["excludes"]
            if isinstance(ex, str):
                if not ex.strip():
                    problems.append(PackProblem(path, "warn", "excludes is an empty string.", where=f"entry:{k}.excludes"))
            elif _is_list_str(ex):
                if not _clean_list_str(ex):
                    problems.append(PackProblem(path, "warn", "excludes list is empty/blank.", where=f"entry:{k}.excludes"))
            else:
                problems.append(PackProblem(path, "error", "excludes must be string or list of strings.", where=f"entry:{k}.excludes"))

        # cross-list fields
        for cf in CROSS_LIST_FIELDS:
            if cf in v and not _is_list_str(v[cf]):
                problems.append(PackProblem(
                    path, "error",
                    f"{cf} must be a list of strings (cross-expansion field).",
                    where=f"entry:{k}.{cf}"
                ))

    return problems


def inspect_packs_folder(root: Path, recursive: bool = True) -> List[PackProblem]:
    root = root.expanduser().resolve()
    pat = "**/*.json" if recursive else "*.json"
    problems: List[PackProblem] = []
    for fp in sorted(root.glob(pat)):
        if fp.is_file():
            problems.extend(inspect_pack_file(fp))
    return problems