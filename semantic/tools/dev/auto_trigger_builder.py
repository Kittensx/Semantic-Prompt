import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Iterable

# -----------------------------
# Normalization
# -----------------------------

_RE_CAMEL = re.compile(r"([a-z])([A-Z])")
_RE_PUNCT = re.compile(r"[^\w\s]")
_RE_WS = re.compile(r"\s+")

def normalize_phrase(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = _RE_CAMEL.sub(r"\1 \2", s)
    s = s.lower()
    s = s.replace("_", " ").replace("-", " ")
    s = _RE_PUNCT.sub(" ", s)
    s = _RE_WS.sub(" ", s)
    return s.strip()


# -----------------------------
# Stopwords / noise controls
# Tune this over time
# -----------------------------

STOPWORDS = {
    "a","an","and","the","or","of","to","in","on","with","for","from","by",
    "style","design","example","examples","variant","variants","variation","variations",
    "set","sets","pack","packs","quality","detail","detailed","generic",
    "photo","photograph","image","picture",  # you may remove if you want these as triggers
}

def looks_too_generic(phrase: str) -> bool:
    # Reject very short, numeric, or pure stopwords
    if not phrase or len(phrase) < 3:
        return True
    if phrase.isdigit():
        return True
    if phrase in STOPWORDS:
        return True
    # reject single token that is too common-y (tune as you see false positives)
    if " " not in phrase and len(phrase) < 4:
        return True
    return False


# -----------------------------
# Candidate model
# -----------------------------

@dataclass
class Candidate:
    phrase_raw: str
    phrase_norm: str
    category: str
    key: str
    source: str        # "alias" | "key"
    base_score: float  # used for conflict resolution


@dataclass
class BuildOptions:
    include_keys: bool = True
    include_aliases: bool = True

    # If you have example packs, you can downrank/skip them
    skip_examples: bool = True
    examples_markers: Tuple[str, ...] = ("_examples", "examples")

    # Candidate limits
    max_candidates_per_entry: int = 40

    # Phrase filtering
    min_tokens_for_phrase: int = 1
    allow_single_token: bool = True

    # Scoring weights
    w_alias: float = 1.00
    w_key: float = 0.70

    # Output
    sort_output: bool = True


# -----------------------------
# Pack scanning helpers
# -----------------------------

def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

def iter_pack_files(
    base_dir: Path,
    packs_dirs: List[Path],
    addons_dir: Optional[Path] = None,
) -> Iterable[Path]:
    # direct roots (core + user)
    for d in packs_dirs:
        if d.exists():
            yield from d.rglob("*.json")

    # addon bundle roots: addons/<addon_name>/packs/**/*.json
    if addons_dir and addons_dir.exists():
        for addon in sorted(addons_dir.iterdir()):
            if not addon.is_dir():
                continue
            pdir = addon / "packs"
            if pdir.exists():
                yield from pdir.rglob("*.json")


def _is_examples_category(cat: str, markers: Tuple[str, ...]) -> bool:
    c = (cat or "").lower()
    return any(m in c for m in markers)


# -----------------------------
# Trigger format conversion
# Keep it compatible with your existing triggers.json style:
#   trigger_phrase -> action mapping
# Here we generate a simple action: category:add:[key]
# (You can adjust later to your richer schema.)
# -----------------------------

def build_action_payload(category: str, key: str) -> Dict[str, Any]:
    # This matches your existing style of mapping top-level group -> { add: [...] }
    # If your system expects different grouping keys than category,
    # swap this to whatever your rewrite engine uses.
    return {
        category: {
            "add": [key]
        }
    }


# -----------------------------
# Core builder
# -----------------------------

def extract_candidates_from_pack(
    pack_path: Path,
    data: Dict[str, Any],
    opts: BuildOptions,
) -> List[Candidate]:
    meta = data.get("_meta") if isinstance(data.get("_meta"), dict) else {}
    category = (meta.get("category") if isinstance(meta, dict) else None) or ""
    if not isinstance(category, str) or not category.strip():
        return []

    category = category.strip().lower()

    # skip example packs (recommended)
    if opts.skip_examples and _is_examples_category(category, opts.examples_markers):
        return []

    out: List[Candidate] = []

    for key, value in data.items():
        if not isinstance(key, str) or key.startswith("_"):
            continue

        canon_key = key.strip()
        if not canon_key:
            continue

        # KEY candidate
        if opts.include_keys:
            phrase_norm = normalize_phrase(canon_key)
            if phrase_norm:
                toks = phrase_norm.split()
                if (len(toks) >= opts.min_tokens_for_phrase) and (opts.allow_single_token or len(toks) >= 2):
                    if not looks_too_generic(phrase_norm):
                        out.append(Candidate(
                            phrase_raw=canon_key,
                            phrase_norm=phrase_norm,
                            category=category,
                            key=canon_key.lower(),  # keep key lookup consistent
                            source="key",
                            base_score=opts.w_key
                        ))

        # ALIAS candidates
        if opts.include_aliases and isinstance(value, dict):
            aliases = value.get("aliases")
            if isinstance(aliases, list):
                count = 0
                for a in aliases:
                    if count >= opts.max_candidates_per_entry:
                        break
                    if not isinstance(a, str):
                        continue
                    a = a.strip()
                    if not a:
                        continue

                    phrase_norm = normalize_phrase(a)
                    if not phrase_norm:
                        continue
                    toks = phrase_norm.split()
                    if (len(toks) >= opts.min_tokens_for_phrase) and (opts.allow_single_token or len(toks) >= 2):
                        if looks_too_generic(phrase_norm):
                            continue
                        out.append(Candidate(
                            phrase_raw=a,
                            phrase_norm=phrase_norm,
                            category=category,
                            key=canon_key.lower(),
                            source="alias",
                            base_score=opts.w_alias
                        ))
                        count += 1

    return out


def score_candidate(c: Candidate) -> float:
    # More tokens = more specific (slight bump)
    toks = c.phrase_norm.split()
    specificity = 1.0 + min(1.5, (len(toks) - 1) * 0.15)
    # Alias beats key by base_score
    return c.base_score * specificity


def build_triggers_from_candidates(
    candidates: List[Candidate],
    *,
    keep_multi_category: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Returns:
      (triggers_map, conflicts_map)

    conflicts_map structure:
      phrase -> list of {category, key, score, source, raw}
    """
    by_phrase: Dict[str, List[Candidate]] = {}
    for c in candidates:
        by_phrase.setdefault(c.phrase_norm, []).append(c)

    triggers: Dict[str, Any] = {}
    conflicts: Dict[str, Any] = {}

    for phrase, cs in by_phrase.items():
        scored = sorted(
            ((score_candidate(c), c) for c in cs),
            key=lambda x: x[0],
            reverse=True
        )

        if not scored:
            continue

        # Detect conflict: multiple distinct (category,key) for the same phrase
        distinct = {}
        for s, c in scored:
            distinct[(c.category, c.key)] = max(distinct.get((c.category, c.key), 0.0), s)

        if len(distinct) > 1:
            conflicts[phrase] = [
                {
                    "category": c.category,
                    "key": c.key,
                    "score": float(s),
                    "source": c.source,
                    "raw": c.phrase_raw,
                }
                for s, c in scored[:25]
            ]

        if keep_multi_category:
            # Map phrase to multiple category actions (dedupe)
            payload: Dict[str, Any] = {}
            seen = set()
            for s, c in scored:
                k = (c.category, c.key)
                if k in seen:
                    continue
                seen.add(k)
                payload.setdefault(c.category, {"add": []})
                payload[c.category]["add"].append(c.key)
            triggers[phrase] = payload
        else:
            # Winner takes all
            best_score, best = scored[0]
            triggers[phrase] = build_action_payload(best.category, best.key)

    return triggers, conflicts


def merge_with_existing_triggers(
    existing: Dict[str, Any],
    generated: Dict[str, Any],
    *,
    prefer_existing: bool = True,
) -> Dict[str, Any]:
    """
    prefer_existing=True:
      - keep existing triggers if they already define a phrase
      - only add new phrases from generated
    """
    out = dict(existing) if isinstance(existing, dict) else {}
    for phrase, payload in generated.items():
        if prefer_existing and phrase in out:
            continue
        out[phrase] = payload
    return out


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_report_md(
    path: Path,
    *,
    total_packs: int,
    total_candidates: int,
    total_triggers: int,
    conflicts_count: int,
    notes: Optional[List[str]] = None,
) -> None:
    lines = []
    lines.append("# Auto Trigger Builder Report")
    lines.append("")
    lines.append(f"- Packs scanned: {total_packs}")
    lines.append(f"- Candidates extracted: {total_candidates}")
    lines.append(f"- Triggers generated: {total_triggers}")
    lines.append(f"- Conflicting phrases: {conflicts_count}")
    lines.append("")
    if notes:
        lines.append("## Notes")
        lines.append("")
        for n in notes:
            lines.append(f"- {n}")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def generate_triggers(
    *,
    base_dir: Path,
    packs_dirs: List[Path],
    addons_dir: Optional[Path],
    existing_triggers_path: Optional[Path],
    out_generated_path: Path,
    out_conflicts_path: Path,
    out_report_path: Path,
    opts: Optional[BuildOptions] = None,
    keep_multi_category: bool = False,
    prefer_existing: bool = True,
) -> Dict[str, Any]:
    """
    Main entry:
      - scans packs
      - generates triggers
      - merges with existing (optional)
      - writes generated + conflicts + report

    Returns generated triggers (final merged).
    """
    opts = opts or BuildOptions()

    pack_files = list(iter_pack_files(base_dir, packs_dirs, addons_dir))
    candidates: List[Candidate] = []

    for fp in pack_files:
        data = _read_json(fp)
        if not isinstance(data, dict):
            continue
        candidates.extend(extract_candidates_from_pack(fp, data, opts))

    generated, conflicts = build_triggers_from_candidates(
        candidates,
        keep_multi_category=keep_multi_category,
    )

    # Merge with existing core triggers.json if provided
    final = generated
    if existing_triggers_path and existing_triggers_path.exists():
        existing = _read_json(existing_triggers_path)
        if isinstance(existing, dict):
            final = merge_with_existing_triggers(existing, generated, prefer_existing=prefer_existing)

    # Deterministic sort (nice diffs)
    if opts.sort_output:
        final = dict(sorted(final.items(), key=lambda x: x[0]))
        conflicts = dict(sorted(conflicts.items(), key=lambda x: x[0]))

    write_json(out_generated_path, final)
    write_json(out_conflicts_path, conflicts)
    write_report_md(
        out_report_path,
        total_packs=len(pack_files),
        total_candidates=len(candidates),
        total_triggers=len(final),
        conflicts_count=len(conflicts),
        notes=[
            "This file is generated. Do not edit by hand; edit packs/aliases instead.",
            "Example packs were skipped (role/examples markers) if skip_examples=True.",
            "Conflicts are expected; review trigger_conflicts.generated.json to tune stopwords or add trigger_hints later.",
        ],
    )

    return final