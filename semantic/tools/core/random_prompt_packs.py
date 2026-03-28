#!/usr/bin/env python3
"""
random_prompt_packs.py

Standalone generator that scans JSON pack files and emits randomized
%%{category=key, ...}%% directive blocks.

Key features:
- --total N: total selections per prompt
- --prints N: how many prompts to generate
- --max-per-category N: cap selections per category (default 2)
- --out FILE: write prompts to file with blank line between entries
- --include-min cats...: categories that must appear at least once (if available)
- --include-any cats...: preferred pool for filling remaining slots
- --include-only cats...: ONLY pick from these categories (hard restriction)
- --other-random N: force N selections from categories outside include-min/include-any
- --exclude cats...: categories to exclude
- --safe: exclude common NSFW-ish categories (simple name-based denylist)

- --subject-category NAME: subject category name (default: subject)
- --no-print: do not print prompts to console

Notes:
- This selects KEYS (the entry names), not raw tags.
- It outputs keys with spaces intact (e.g. socks=thigh highs).
"""

from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set

SPACE_RE = re.compile(r"\s+")
SCRIPT_PATH = Path(__file__).resolve()
SEMANTIC_ROOT = SCRIPT_PATH.parents[2]   # .../semantic
PACKS_ROOT = SEMANTIC_ROOT / "packs"
OUTPUT_ROOT = SEMANTIC_ROOT / "random_generator_ideas"

def norm(s: str) -> str:
    return SPACE_RE.sub(" ", (s or "")).strip()


def norm_list(items: Optional[List[str]]) -> List[str]:
    if not items:
        return []
    out: List[str] = []
    for x in items:
        x = norm(x)
        if x:
            out.append(x)
    return out


# Basic "safe mode" denylist — name-based, easy to tune.
DEFAULT_SAFE_EXCLUDES: Set[str] = {
    "fetish_ballgags",
    "fetish_clothing",
    "fetish_collars",
    "fetish_ears",
    "fetish_furniture",
    "fetish_leash",
    "fetish_pony",
    "fetish_shackles",
    "fetish_shibari",
    "accessories_nsfw",
    "lingerie",
    "nudity",
    "nsfw",
}


def load_pack(path: Path) -> Tuple[str, List[str]]:
    """Return (category, keys) from a pack JSON."""
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        return (norm(path.stem), [])

    meta = data.get("_meta")
    category = None
    if isinstance(meta, dict):
        category = meta.get("category")

    category = norm(category) if category else norm(path.stem)

    keys: List[str] = []
    for k in data.keys():
        if k == "_meta":
            continue
        if isinstance(k, str):
            k2 = norm(k)
            if k2:
                keys.append(k2)

    # de-dup, stable order
    seen = set()
    out: List[str] = []
    for k in keys:
        if k not in seen:
            out.append(k)
            seen.add(k)

    return category, out


def scan_packs(folder: Path) -> Dict[str, List[str]]:
    """Scan folder recursively for *.json and build category -> keys mapping."""
    packs: Dict[str, List[str]] = {}
    for p in sorted(folder.rglob("*.json")):
        cat, keys = load_pack(p)
        if not cat or not keys:
            continue
        packs.setdefault(cat, []).extend(keys)

    # de-dup per category
    for cat, keys in list(packs.items()):
        seen = set()
        deduped: List[str] = []
        for k in keys:
            if k not in seen:
                deduped.append(k)
                seen.add(k)
        packs[cat] = deduped

    return packs


def _canon_part(part: str) -> str:
    p = norm(part).lower()
    if p.endswith("ies") and len(p) > 3:
        return p[:-3] + "y"
    if p.endswith("s") and not p.endswith("ss") and len(p) > 3:
        return p[:-1]
    return p


def _parts_equal(a: str, b: str) -> bool:
    return _canon_part(a) == _canon_part(b)


def _cat_parts(cat: str) -> List[str]:
    return [part for part in norm(cat).lower().split(".") if part]


def _shorthand_score(query_parts: List[str], candidate_parts: List[str]) -> int:
    """
    Score whether a shorthand category query can match a full category.

    Exact matches are best.
    Suffix matches are strong.
    Ordered-subsequence matches allow skipping segments in the middle, such as:
      skirts.length -> clothing.garments.bottoms.skirts.mod.length
    """
    if not query_parts or not candidate_parts:
        return -1

    if len(query_parts) == len(candidate_parts) and all(_parts_equal(a, b) for a, b in zip(query_parts, candidate_parts)):
        return 1000 - len(candidate_parts)

    qlen = len(query_parts)
    clen = len(candidate_parts)

    if qlen <= clen and all(_parts_equal(a, b) for a, b in zip(query_parts, candidate_parts[-qlen:])):
        return 900 - len(candidate_parts)

    i = 0
    for part in candidate_parts:
        if i < qlen and _parts_equal(part, query_parts[i]):
            i += 1
    if i == qlen:
        return 700 - len(candidate_parts)

    return -1


def expand_category_refs(
    refs: Optional[List[str]],
    available_categories: List[str],
) -> List[str]:
    """
    Expand shorthand category references into full categories.

    Examples:
      skirts.length -> clothing.garments.bottoms.skirts.mod.length
      lipstick.color -> appearance.makeup.lipstick.mod.color

    If multiple categories tie for the best match, all best matches are returned.
    If nothing matches, the original ref is preserved.
    """
    if not refs:
        return []

    available = []
    seen_available = set()
    for cat in available_categories:
        c = norm(cat)
        if c and c not in seen_available:
            available.append(c)
            seen_available.add(c)

    out: List[str] = []
    seen_out: Set[str] = set()

    for raw_ref in refs:
        ref = norm(raw_ref)
        if not ref:
            continue

        if ref in seen_available:
            if ref not in seen_out:
                out.append(ref)
                seen_out.add(ref)
            continue

        query_parts = _cat_parts(ref)
        matches: List[tuple[int, str]] = []
        for cat in available:
            score = _shorthand_score(query_parts, _cat_parts(cat))
            if score >= 0:
                matches.append((score, cat))

        if not matches:
            if ref not in seen_out:
                out.append(ref)
                seen_out.add(ref)
            continue

        best_score = max(score for score, _ in matches)
        best_cats = sorted(cat for score, cat in matches if score == best_score)
        for cat in best_cats:
            if cat not in seen_out:
                out.append(cat)
                seen_out.add(cat)

    return out


def format_directive(items: List[Tuple[str, str]]) -> str:
    return "%%{" + ", ".join(f"{c}={k}" for c, k in items) + "}%%"


def pick_unique_key(
    rng: random.Random,
    keys: List[str],
    used_pairs: Set[Tuple[str, str]],
    category: str,
    max_attempts: int = 200,
) -> Optional[str]:
    """Pick a (category,key) that hasn't been used in this prompt yet."""
    if not keys:
        return None
    for _ in range(max_attempts):
        k = rng.choice(keys)
        if (category, k) not in used_pairs:
            return k
    # fallback: allow repeats if category keys list is tiny
    return rng.choice(keys) if keys else None


def choose_items(
    packs: Dict[str, List[str]],
    total: int,
    max_per_category: int,
    rng: random.Random,
    include_min: Optional[List[str]] = None,
    include_any: Optional[List[str]] = None,
    include_only: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
    safe: bool = False,
    subject_category: str = "subject",
    other_random: int = 0,
    debug_resolve: bool = False,
) -> List[Tuple[str, str]]:
    """
    Build a list of (category, key) selections for ONE prompt.
    Supports shorthand category refs like skirts.length.
    """
    include_min_n = norm_list(include_min)
    include_any_n = norm_list(include_any)
    include_only_n = norm_list(include_only)
    exclude_n = norm_list(exclude)

    # Normalize available categories first so shorthand refs can resolve
    all_available_categories = [norm(cat) for cat in packs.keys() if norm(cat)]

    include_min_resolved = expand_category_refs(include_min_n, all_available_categories)
    include_any_resolved = expand_category_refs(include_any_n, all_available_categories)
    include_only_resolved = expand_category_refs(include_only_n, all_available_categories)
    exclude_resolved = expand_category_refs(exclude_n, all_available_categories)

    if debug_resolve:
        print("[resolve] include-min :", include_min_n, "->", include_min_resolved)
        print("[resolve] include-any :", include_any_n, "->", include_any_resolved)
        print("[resolve] include-only:", include_only_n, "->", include_only_resolved)
        print("[resolve] exclude     :", exclude_n, "->", exclude_resolved)

    exclude_set = set(exclude_resolved)
    include_only_set: Optional[Set[str]] = set(include_only_resolved) if include_only_resolved else None

    # Apply safe excludes
    if safe:
        exclude_set |= set(DEFAULT_SAFE_EXCLUDES)

    subject_category_n = norm(subject_category) or "subject"

    # Build normalized packs filtered by excludes and include_only restriction
    norm_packs: Dict[str, List[str]] = {}
    for cat, keys in packs.items():
        c = norm(cat)
        if not c or c in exclude_set:
            continue
        if include_only_set is not None and c not in include_only_set:
            continue

        kk = [norm(k) for k in keys if norm(k)]
        if kk:
            norm_packs[c] = kk

    if not norm_packs:
        return []

    all_categories = list(norm_packs.keys())

    # Keep only resolved categories that survived filtering
    include_min_n = [c for c in include_min_resolved if c in norm_packs]
    include_any_n = [c for c in include_any_resolved if c in norm_packs]

    min_set = set(include_min_n)
    any_set = set(include_any_n)

    chosen: List[Tuple[str, str]] = []
    used_pairs: Set[Tuple[str, str]] = set()
    per_cat_count: Dict[str, int] = {}

    def can_pick_cat(cat: str) -> bool:
        return per_cat_count.get(cat, 0) < max_per_category and bool(norm_packs.get(cat))

    def add_pick(cat: str) -> bool:
        if not can_pick_cat(cat):
            return False
        key = pick_unique_key(rng, norm_packs[cat], used_pairs, cat)
        if not key:
            return False
        chosen.append((cat, key))
        used_pairs.add((cat, key))
        per_cat_count[cat] = per_cat_count.get(cat, 0) + 1
        return True

    # Prefer subject category first when available and not excluded
    if len(chosen) < total and subject_category_n in norm_packs:
        add_pick(subject_category_n)

    # 1) include-min: each at least once if possible
    for cat in include_min_n:
        if len(chosen) >= total:
            break
        add_pick(cat)

    preferred_pool = [c for c in include_any_n if c in norm_packs and c not in min_set]
    other_pool = [c for c in all_categories if c not in min_set and c not in any_set]

    # 2) Force other_random picks from categories outside include-min/include-any
    attempts = 0
    while other_random > 0 and len(chosen) < total and attempts < 10000:
        attempts += 1
        if not other_pool:
            break
        cat = rng.choice(other_pool)
        if add_pick(cat):
            other_random -= 1

    # 3) Fill the rest
    attempts = 0
    while len(chosen) < total and attempts < 20000:
        attempts += 1

        pool = preferred_pool if preferred_pool else all_categories
        if not pool:
            break

        cat = rng.choice(pool)

        # If preferred pool is exhausted by caps, fall back to all categories
        if preferred_pool and not can_pick_cat(cat):
            cat = rng.choice(all_categories)

        add_pick(cat)

        if attempts % 2000 == 0:
            if not any(can_pick_cat(c) for c in all_categories):
                break

    return chosen[:total]


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate randomized %%{...}%% prompts from JSON packs."
    )
    ap.add_argument(
        "--packs",
        default=str(PACKS_ROOT),
        help="Folder containing pack JSONs (recursive). Defaults to semantic/packs.",
    )
    ap.add_argument("--total", type=int, default=6, help="Selections per prompt.")
    ap.add_argument("--prints", type=int, default=1, help="Number of prompts to generate.")
    ap.add_argument("--max-per-category", type=int, default=2, help="Max selections per category.")
    ap.add_argument("--out", type=str, default=None, help="Write prompts to this text file.")
    ap.add_argument("--no-print", action="store_true", help="Do not print prompts to console.")

    ap.add_argument(
        "--include-min",
        nargs="*",
        default=None,
        help="Categories that must appear at least once. Supports shorthand like skirts.length.",
    )
    ap.add_argument(
        "--include-any",
        nargs="*",
        default=None,
        help="Preferred pool for filling remaining slots. Supports shorthand like skirts.length.",
    )
    ap.add_argument(
        "--include-only",
        nargs="*",
        default=None,
        help="Restrict selection to ONLY these categories (hard restriction). Supports shorthand like skirts.length.",
    )
    ap.add_argument(
        "--other-random",
        type=int,
        default=0,
        help="Force this many picks from categories outside include-min/include-any.",
    )

    ap.add_argument("--exclude", nargs="*", default=None, help="Exclude these categories. Supports shorthand like skirts.length.")
    ap.add_argument("--debug-resolve", action="store_true", help="Print how shorthand category refs were expanded.")
    ap.add_argument(
        "--safe",
        action="store_true",
        help="Exclude common NSFW-ish category names (simple denylist).",
    )

    
    ap.add_argument(
        "--subject-category",
        default="subject",
        help="Category name used for subject (default: subject).",
    )

    args = ap.parse_args()

    packs_dir = Path(args.packs).expanduser()
    if not packs_dir.is_absolute():
        packs_dir = (SEMANTIC_ROOT / packs_dir).resolve()
    else:
        packs_dir = packs_dir.resolve()

    if not packs_dir.exists() or not packs_dir.is_dir():
        raise SystemExit(f"--packs must be a directory: {packs_dir}")
    

    if args.total <= 0:
        raise SystemExit("--total must be > 0")
    if args.prints <= 0:
        raise SystemExit("--prints must be > 0")
    if args.max_per_category <= 0:
        raise SystemExit("--max-per-category must be > 0")

    packs = scan_packs(packs_dir)
    if not packs:
        raise SystemExit(f"No pack JSON files found in: {packs_dir}")

    rng = random.Random()  # no seed control by design

    prompts: List[str] = []
    for _ in range(args.prints):
        items = choose_items(
            packs=packs,
            total=args.total,
            max_per_category=args.max_per_category,
            rng=rng,
            include_min=args.include_min,
            include_any=args.include_any,
            include_only=args.include_only,  # NEW
            exclude=args.exclude,
            safe=args.safe,            
            subject_category=args.subject_category,
            other_random=args.other_random,
            debug_resolve=args.debug_resolve,
        )
        prompts.append(format_directive(items))

    # Print
    if not args.no_print:
        for p in prompts:
            print(p)
            print()

    
    # Write to file
    out_path = None
    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = OUTPUT_ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if out_path:
            with out_path.open("w", encoding="utf-8") as f:
                for p in prompts:
                    f.write(p + "\n\n")
            print(f"\nSaved {len(prompts)} prompts to: {out_path}")


if __name__ == "__main__":
    main()