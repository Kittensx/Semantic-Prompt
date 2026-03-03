#!/usr/bin/env python3
"""
random_prompt_packs.py

Bundled CLI tool for exploring this project's JSON pack library.

Design goals (v1):
- Packs are stored under a single root folder (default: ../packs relative to this script).
- Users can select packs by category name (from _meta.category or filename stem).
- Users can deny entire directories (relative to packs root) to block large groups of packs.
- Outputs randomized %%{category=key, ...}%% directives for quick exploration/testing.

Note:
Generated prompts reflect the content of the selected packs. Users are responsible for ensuring
appropriate and compliant use with their target platform(s).
"""

from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set


SPACE_RE = re.compile(r"\s+")


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
    out = []
    for k in keys:
        if k not in seen:
            out.append(k)
            seen.add(k)

    return category, out


def _is_denied(rel_parts: Tuple[str, ...], deny_dirs: Set[str]) -> bool:
    """True if any path segment equals one of the denied directory names."""
    if not deny_dirs:
        return False
    parts_set = set(rel_parts)
    # match on path segments only (not substring)
    return any(d in parts_set for d in deny_dirs)


def scan_packs(packs_root: Path, deny_dirs: Optional[List[str]] = None) -> Dict[str, List[str]]:
    """
    Scan packs_root recursively for *.json and build category -> keys mapping.

    deny_dirs:
      list of directory names (path segments) to skip, relative to packs_root.
      Example: deny 'nsfw' will skip packs_root/**/nsfw/**/*.json
    """
    deny = {norm(d) for d in (deny_dirs or []) if norm(d)}
    packs: Dict[str, List[str]] = {}

    for p in sorted(packs_root.rglob("*.json")):
        try:
            rel_parts = p.relative_to(packs_root).parts
        except Exception:
            rel_parts = p.parts

        # skip if any denied segment appears in the relative path
        if _is_denied(tuple(rel_parts), deny):
            continue

        try:
            cat, keys = load_pack(p)
        except Exception:
            # If a JSON is malformed, skip it rather than crashing V1
            continue

        if not cat or not keys:
            continue

        packs.setdefault(cat, []).extend(keys)

    # de-dup per category
    for cat, keys in list(packs.items()):
        seen = set()
        deduped = []
        for k in keys:
            if k not in seen:
                deduped.append(k)
                seen.add(k)
        packs[cat] = deduped

    return packs


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
    exclude: Optional[List[str]] = None,
    safe: bool = False,
    require_subject: bool = True,
    subject_category: str = "subject",
    other_random: int = 0,
) -> List[Tuple[str, str]]:
    """
    Build a list of (category, key) selections for ONE prompt.
    """
    include_min = norm_list(include_min)
    include_any = norm_list(include_any)
    exclude_set = set(norm_list(exclude))

    # Apply safe excludes
    if safe:
        exclude_set |= set(DEFAULT_SAFE_EXCLUDES)

    subject_category = norm(subject_category) or "subject"

    # Build normalized packs filtered by excludes
    norm_packs: Dict[str, List[str]] = {}
    for cat, keys in packs.items():
        c = norm(cat)
        if not c or c in exclude_set:
            continue
        kk = [norm(k) for k in keys if norm(k)]
        if kk:
            norm_packs[c] = kk

    if not norm_packs:
        return []

    # Enforce subject existence if required
    if require_subject and subject_category not in norm_packs:
        # In V1, fail gracefully with a clear message
        return []

    # Helper pools
    all_categories = list(norm_packs.keys())
    min_set = set(include_min)
    any_set = set(include_any)

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

    # 0) Subject first (helps your engine “anchor” prompts)
    if require_subject:
        add_pick(subject_category)

    # 1) include-min: each at least once if possible
    for cat in include_min:
        if len(chosen) >= total:
            break
        if cat in norm_packs:
            add_pick(cat)

    # Pools:
    preferred_pool = [c for c in include_any if c in norm_packs and c not in min_set]
    other_pool = [c for c in all_categories if c not in min_set and c not in any_set]

    # 2) Force other_random picks from "other" categories
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

        # If preferred pool is exhausted by caps, fall back to all_categories
        if preferred_pool and not can_pick_cat(cat):
            cat2 = rng.choice(all_categories)
            add_pick(cat2)
        else:
            add_pick(cat)

        # Quick exit if we’re basically stuck (all categories capped or empty)
        if attempts % 2000 == 0:
            pickable = any(can_pick_cat(c) for c in all_categories)
            if not pickable:
                break

    return chosen[:total]


def main():
    ap = argparse.ArgumentParser(
        description="Generate randomized %%{...}%% prompts from JSON packs."
    )

    default_root = (Path(__file__).resolve().parent.parent / "packs").resolve()

    ap.add_argument(
        "--packs-root",
        default=str(default_root),
        help="Root folder containing JSON packs (default: ../packs relative to this tool).",
    )

    ap.add_argument(
        "--use",
        nargs="*",
        default=None,
        help="Optional list of category names to restrict generation to (matches _meta.category or filename stem).",
    )

    ap.add_argument(
        "--deny-dir",
        nargs="*",
        default=None,
        help="Deny any packs located under directories with these names (path segment match, relative to packs-root).",
    )

    ap.add_argument("--list-categories", action="store_true", help="List available categories and exit.")
    ap.add_argument("--total", type=int, default=6, help="Selections per prompt.")
    ap.add_argument("--prints", type=int, default=1, help="Number of prompts to generate.")
    ap.add_argument("--max-per-category", type=int, default=2, help="Max selections per category.")
    ap.add_argument("--out", type=str, default=None, help="Write prompts to this text file.")
    ap.add_argument("--no-print", action="store_true", help="Do not print prompts to console.")

    ap.add_argument("--include-min", nargs="*", default=None,
                    help="Categories that must appear at least once (if available).")
    ap.add_argument("--include-any", nargs="*", default=None,
                    help="Preferred pool for filling remaining slots.")
    ap.add_argument("--other-random", type=int, default=0,
                    help="Force this many picks from categories outside include-min/include-any.")

    ap.add_argument("--exclude", nargs="*", default=None, help="Exclude these categories.")
    ap.add_argument("--safe", action="store_true",
                    help="Enable best-effort filtering of explicitly named adult/fetish categories.")

    ap.add_argument("--no-require-subject", action="store_true",
                    help="Do not force a subject selection.")
    ap.add_argument("--subject-category", default="subject",
                    help="Category name used for subject (default: subject).")

    args = ap.parse_args()

    packs_root = Path(args.packs_root).expanduser().resolve()
    if not packs_root.exists() or not packs_root.is_dir():
        raise SystemExit(f"--packs-root must be a directory: {packs_root}")

    if args.total <= 0:
        raise SystemExit("--total must be > 0")
    if args.prints <= 0:
        raise SystemExit("--prints must be > 0")
    if args.max_per_category <= 0:
        raise SystemExit("--max-per-category must be > 0")

    packs = scan_packs(packs_root, deny_dirs=args.deny_dir)
    if not packs:
        raise SystemExit(f"No pack JSON files found in: {packs_root}")

    if args.list_categories:
        for cat in sorted(packs.keys()):
            print(cat)
        return

    # Restrict to requested categories (if provided)
    use = set(norm_list(args.use))
    if use:
        missing = sorted([c for c in use if c not in packs])
        packs = {c: packs[c] for c in packs.keys() if c in use}
        if missing:
            print("[WARN] Requested categories not found (after deny-dir filtering):")
            for m in missing:
                print(f"  - {m}")
        if not packs:
            raise SystemExit("No categories left after applying --use (and deny-dir).")

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
            exclude=args.exclude,
            safe=args.safe,
            require_subject=not args.no_require_subject,
            subject_category=args.subject_category,
            other_random=args.other_random,
        )

        if not items:
            # give a helpful hint if we fail (usually subject missing or over-excluded)
            if not args.no_print:
                print("[WARN] Could not generate a prompt with current constraints (try relaxing excludes/deny-dir).")
            continue

        prompts.append(format_directive(items))

    # Print
    if not args.no_print:
        for p in prompts:
            print(p)
            print()

    # Write to file
    if args.out:
        out_path = Path(args.out).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            for i, p in enumerate(prompts):
                f.write(p)
                if i < len(prompts) - 1:
                    f.write("\n\n")

        if not args.no_print:
            print(f"Saved {len(prompts)} prompts to: {out_path}")


if __name__ == "__main__":
    main()