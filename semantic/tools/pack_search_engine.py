#!/usr/bin/env python3
"""
pack_search_engine.py

Backend search engine for Semantic Prompt packs.

Purpose
-------
- Search pack entries by user-entered text
- Rank likely matches
- Return prompt-ready results in either:
    category:key
    category=key
- Return entry definitions / payload for inspection
- Support CLI-first testing before UI integration

Design notes
------------
- Entry-first search: results point to a specific entry key, not just a pack.
- Schema-tolerant: supports lean packs (key + tags only) and richer packs with
  aliases / related / requires / excludes / negative / extra text fields.
- Default mode is forgiving:
    * case-insensitive
    * underscores, hyphens, spaces treated as equivalent
    * plural/singular tolerant
- Optional match-case mode:
    * literal-first search preserving case and separators
    * normalized fallback still allowed, but ranks lower
- Optional advanced query directives:
    * rank field:value
    * ignore field

Example usage
-------------
python pack_search_engine.py "cutouts" --packs-root "C:/.../semantic/packs"
python pack_search_engine.py "double cutouts" --packs-root "C:/.../semantic/packs"
python pack_search_engine.py "double_cut" --packs-root "C:/.../semantic/packs" --match-case
python pack_search_engine.py "cutouts rank meta.search_tags:1.2 ignore meta.notes" \
  --packs-root "C:/.../semantic/packs" --advanced
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


# ============================================================
# Search Rules / Constants
# ============================================================

KNOWN_ENTRY_FIELDS = {
    "tags",
    "aliases",
    "related",
    "requires",
    "excludes",
    "negative",
}

KNOWN_SEARCH_FIELDS = {
    "key",
    "entry.tags",
    "entry.aliases",
    "entry.related",
    "entry.requires",
    "entry.excludes",
    "entry.negative",
    "meta.category",
    "meta.title",
    "meta.notes",
    "meta.aliases",
    "meta.search_tags",
    "meta.related_categories",
}

# Default field weights. Higher = stronger ranking contribution.
DEFAULT_FIELD_WEIGHTS: Dict[str, float] = {
    "key": 120.0,
    "entry.aliases": 95.0,
    "meta.aliases": 80.0,
    "meta.search_tags": 72.0,
    "entry.tags": 65.0,
    "meta.title": 42.0,
    "meta.notes": 28.0,
    "entry.related": 24.0,
    "entry.requires": 20.0,
    "entry.excludes": 16.0,
    "entry.negative": 12.0,
    "meta.related_categories": 10.0,
}

FIELD_MODE_MULTIPLIERS: Dict[str, float] = {
    "ignored": 0.0,
    "normal": 1.0,
    "high": 1.6,
}

PRESET_FIELD_MODES: Dict[str, Dict[str, str]] = {
    "prompt": {
        "key": "high",
        "entry.aliases": "high",
        "entry.tags": "high",
        "meta.aliases": "normal",
        "meta.search_tags": "normal",
        "meta.title": "normal",
        "meta.notes": "ignored",
        "entry.related": "ignored",
        "entry.requires": "ignored",
        "entry.excludes": "ignored",
        "entry.negative": "ignored",
        "meta.related_categories": "ignored",
    },
    "exact_key": {
        "key": "high",
        "entry.aliases": "normal",
        "entry.tags": "ignored",
        "meta.aliases": "ignored",
        "meta.search_tags": "ignored",
        "meta.title": "ignored",
        "meta.notes": "ignored",
        "entry.related": "ignored",
        "entry.requires": "ignored",
        "entry.excludes": "ignored",
        "entry.negative": "ignored",
        "meta.related_categories": "ignored",
    },
    "broad": {
        "key": "high",
        "entry.aliases": "high",
        "entry.tags": "normal",
        "meta.aliases": "normal",
        "meta.search_tags": "high",
        "meta.title": "normal",
        "meta.notes": "normal",
        "entry.related": "normal",
        "entry.requires": "ignored",
        "entry.excludes": "ignored",
        "entry.negative": "ignored",
        "meta.related_categories": "normal",
    },
    "relationships": {
        "key": "normal",
        "entry.aliases": "normal",
        "entry.tags": "normal",
        "meta.aliases": "ignored",
        "meta.search_tags": "ignored",
        "meta.title": "normal",
        "meta.notes": "normal",
        "entry.related": "high",
        "entry.requires": "high",
        "entry.excludes": "high",
        "entry.negative": "ignored",
        "meta.related_categories": "high",
    },
    "debug": {
        "key": "high",
        "entry.aliases": "high",
        "entry.tags": "high",
        "meta.aliases": "high",
        "meta.search_tags": "high",
        "meta.title": "normal",
        "meta.notes": "normal",
        "entry.related": "normal",
        "entry.requires": "normal",
        "entry.excludes": "normal",
        "entry.negative": "normal",
        "meta.related_categories": "normal",
    },
}

WORD_SPLIT_RE = re.compile(r"[\s_\-./\\:;,+(){}\[\]|]+")
NORMALIZE_SEP_RE = re.compile(r"[\s_\-]+")
ADVANCED_RANK_RE = re.compile(r"\brank\s+([A-Za-z0-9_.]+):([0-9]*\.?[0-9]+)\b")
ADVANCED_IGNORE_RE = re.compile(r"\bignore\s+([A-Za-z0-9_.]+)\b")


# ============================================================
# Data Models
# ============================================================

@dataclass
class SearchOptions:
    packs_root: Path
    display_format: str = "colon"   # colon | equals
    match_case: bool = False
    max_results: int = 25
    show_definitions: bool = False
    json_output: bool = False
    preset: str = "prompt"
    field_modes: Dict[str, str] = field(default_factory=dict)
    advanced: bool = False
    show_warnings: bool = True


@dataclass
class AdvancedDirectives:
    rank_overrides: Dict[str, float] = field(default_factory=dict)
    ignored_fields: set[str] = field(default_factory=set)
    warnings: List[str] = field(default_factory=list)
    raw_directives: List[str] = field(default_factory=list)


@dataclass
class IndexedFieldValue:
    field_name: str
    original: str
    normalized: str
    raw_tokens: List[str]
    base_tokens: List[str]


@dataclass
class EntryDefinition:
    category: str
    key: str
    file: str
    meta: Dict[str, Any]
    entry_fields: Dict[str, Any]
    extra_fields: Dict[str, Any]


@dataclass
class IndexedEntry:
    category: str
    key: str
    file: str
    meta: Dict[str, Any]
    entry_fields: Dict[str, Any]
    extra_fields: Dict[str, Any]
    searchable_fields: List[IndexedFieldValue] = field(default_factory=list)


@dataclass
class MatchEvidence:
    field_name: str
    reason: str
    score: float
    matched_value: str


@dataclass
class SearchResult:
    category: str
    key: str
    file: str
    score: float
    display_text: str
    matched_fields: List[str]
    reasons: List[str]
    evidences: List[MatchEvidence]
    definition: EntryDefinition


# ============================================================
# Formatting Helpers
# ============================================================

def format_prompt_token(category: str, key: str, display_format: str) -> str:
    sep = ":" if display_format == "colon" else "="
    return f"{category}{sep}{key}"


# ============================================================
# Normalization Helpers
# ============================================================

def safe_list_of_strings(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if isinstance(v, (str, int, float))]
    return []


def normalize_text(text: str) -> str:
    text = text.strip().lower()
    text = NORMALIZE_SEP_RE.sub(" ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize_text(text: str, *, keep_case: bool = False) -> List[str]:
    value = text.strip() if keep_case else text.strip().lower()
    parts = [p for p in WORD_SPLIT_RE.split(value) if p]
    return parts


def singularize_token(token: str) -> str:
    """
    Lightweight plural normalization.

    Conservative by design; avoids over-stemming.
    """
    t = token.lower()
    if len(t) <= 3:
        return t
    if t.endswith("ies") and len(t) > 4:
        return t[:-3] + "y"
    if t.endswith("sses"):
        return t[:-2]  # dresses -> dress
    if t.endswith("xes") or t.endswith("zes") or t.endswith("ches") or t.endswith("shes"):
        return t[:-2]
    if t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t


def base_tokens(text: str, *, keep_case: bool = False) -> List[str]:
    tokens = tokenize_text(text, keep_case=keep_case)
    if keep_case:
        # preserve case for literal display, but singular logic still uses lowercase-ish normalization
        return [singularize_token(t) for t in tokens]
    return [singularize_token(t) for t in tokens]


def base_phrase(text: str) -> str:
    return " ".join(base_tokens(text))


# ============================================================
# Advanced Search Parsing
# ============================================================

def parse_advanced_query(raw_query: str, enabled: bool) -> Tuple[str, AdvancedDirectives]:
    directives = AdvancedDirectives()

    if not enabled:
        return raw_query.strip(), directives

    working = raw_query

    for match in ADVANCED_RANK_RE.finditer(raw_query):
        field_name = match.group(1)
        try:
            multiplier = float(match.group(2))
        except ValueError:
            continue
        directives.rank_overrides[field_name] = multiplier
        directives.raw_directives.append(f"rank {field_name}:{multiplier}")
        working = working.replace(match.group(0), " ")

    for match in ADVANCED_IGNORE_RE.finditer(raw_query):
        field_name = match.group(1)
        directives.ignored_fields.add(field_name)
        directives.raw_directives.append(f"ignore {field_name}")
        working = working.replace(match.group(0), " ")

    base_query = re.sub(r"\s+", " ", working).strip()
    return base_query, directives


# ============================================================
# Field Policy Resolution
# ============================================================

def resolve_field_modes(
    options: SearchOptions,
    directives: AdvancedDirectives,
) -> Tuple[Dict[str, str], Dict[str, float], List[str]]:
    warnings: List[str] = []
    modes: Dict[str, str] = {name: "normal" for name in KNOWN_SEARCH_FIELDS}

    preset_modes = PRESET_FIELD_MODES.get(options.preset, {})
    for field_name, mode in preset_modes.items():
        if field_name in KNOWN_SEARCH_FIELDS and mode in FIELD_MODE_MULTIPLIERS:
            modes[field_name] = mode

    for field_name, mode in options.field_modes.items():
        if field_name not in KNOWN_SEARCH_FIELDS and not field_name.startswith("entry.other."):
            warnings.append(f"Unknown field in --field-mode: {field_name}")
            continue
        if mode not in FIELD_MODE_MULTIPLIERS:
            warnings.append(f"Unknown field mode for {field_name}: {mode}")
            continue
        modes[field_name] = mode

    for field_name in directives.ignored_fields:
        if field_name not in KNOWN_SEARCH_FIELDS and not field_name.startswith("entry.other."):
            warnings.append(f"Unknown field in advanced ignore: {field_name}")
            continue
        modes[field_name] = "ignored"

    effective_weights: Dict[str, float] = {}

    for field_name, mode in modes.items():
        base_weight = DEFAULT_FIELD_WEIGHTS.get(field_name, 8.0 if field_name.startswith("entry.other.") else 0.0)
        effective_weights[field_name] = base_weight * FIELD_MODE_MULTIPLIERS.get(mode, 1.0)

    for field_name, multiplier in directives.rank_overrides.items():
        if field_name not in KNOWN_SEARCH_FIELDS and not field_name.startswith("entry.other."):
            warnings.append(f"Unknown field in advanced rank: {field_name}")
            continue
        if modes.get(field_name) == "ignored":
            continue
        base_weight = effective_weights.get(field_name, DEFAULT_FIELD_WEIGHTS.get(field_name, 8.0))
        effective_weights[field_name] = base_weight * multiplier

    return modes, effective_weights, warnings


# ============================================================
# Pack Loading / Index Building
# ============================================================

def read_json_file(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def build_indexed_field(field_name: str, value: str) -> IndexedFieldValue:
    return IndexedFieldValue(
        field_name=field_name,
        original=value,
        normalized=normalize_text(value),
        raw_tokens=tokenize_text(value, keep_case=True),
        base_tokens=base_tokens(value),
    )


def extract_searchable_fields(
    category: str,
    meta: Dict[str, Any],
    key: str,
    entry: Dict[str, Any],
) -> Tuple[List[IndexedFieldValue], Dict[str, Any], Dict[str, Any]]:
    searchable: List[IndexedFieldValue] = []
    known_entry_fields: Dict[str, Any] = {}
    extra_fields: Dict[str, Any] = {}

    # Primary key field
    searchable.append(build_indexed_field("key", key))

    # Meta fields
    meta_mapping = {
        "meta.category": meta.get("category", category),
        "meta.title": meta.get("title", ""),
        "meta.notes": meta.get("notes", ""),
        "meta.aliases": meta.get("aliases", []),
        "meta.search_tags": meta.get("search_tags", []),
        "meta.related_categories": meta.get("related_categories", []),
    }

    for field_name, value in meta_mapping.items():
        values = safe_list_of_strings(value)
        for item in values:
            if item.strip():
                searchable.append(build_indexed_field(field_name, item))

    for entry_field_name, value in entry.items():
        field_name = f"entry.{entry_field_name}"
        values = safe_list_of_strings(value)

        if entry_field_name in KNOWN_ENTRY_FIELDS:
            known_entry_fields[entry_field_name] = value
            for item in values:
                if item.strip():
                    searchable.append(build_indexed_field(field_name, item))
        else:
            if values:
                extra_fields[entry_field_name] = value
                extra_name = f"entry.other.{entry_field_name}"
                for item in values:
                    if item.strip():
                        searchable.append(build_indexed_field(extra_name, item))
            else:
                # Preserve non-text extras for the definition payload even if not searchable.
                extra_fields[entry_field_name] = value

    return searchable, known_entry_fields, extra_fields


def index_pack_file(path: Path) -> List[IndexedEntry]:
    data = read_json_file(path)
    if not data:
        return []

    meta = data.get("_meta", {})
    if not isinstance(meta, dict):
        meta = {}

    category = str(meta.get("category", "")).strip()
    if not category:
        return []

    indexed_entries: List[IndexedEntry] = []

    for top_key, value in data.items():
        if top_key.startswith("_"):
            continue
        if not isinstance(value, dict):
            continue

        searchable, known_fields, extra_fields = extract_searchable_fields(
            category=category,
            meta=meta,
            key=top_key,
            entry=value,
        )

        indexed_entries.append(
            IndexedEntry(
                category=category,
                key=top_key,
                file=str(path),
                meta=meta,
                entry_fields=known_fields,
                extra_fields=extra_fields,
                searchable_fields=searchable,
            )
        )

    return indexed_entries


def build_index(packs_root: Path) -> List[IndexedEntry]:
    entries: List[IndexedEntry] = []
    for path in sorted(packs_root.rglob("*.json")):
        entries.extend(index_pack_file(path))
    return entries


# ============================================================
# Matching / Scoring
# ============================================================

def phrase_from_tokens(tokens: Sequence[str]) -> str:
    return " ".join(tokens).strip()


def token_overlap_ratio(query_tokens: Sequence[str], candidate_tokens: Sequence[str]) -> float:
    if not query_tokens or not candidate_tokens:
        return 0.0
    q = set(query_tokens)
    c = set(candidate_tokens)
    return len(q & c) / max(len(q), 1)
def has_exact_token_match(query_tokens: Sequence[str], candidate_tokens: Sequence[str]) -> bool:
    if not query_tokens or not candidate_tokens:
        return False
    if len(query_tokens) != 1:
        return False
    q = query_tokens[0]
    return q in candidate_tokens


def has_token_sequence_match(query_tokens: Sequence[str], candidate_tokens: Sequence[str]) -> bool:
    """
    True when query tokens appear as a contiguous token sequence.
    Example:
      query:    ["eagle", "lion"]
      candidate:["griffin", "eagle", "lion", "hybrid"]
      -> True
    """
    if not query_tokens or not candidate_tokens:
        return False
    qlen = len(query_tokens)
    clen = len(candidate_tokens)
    if qlen > clen:
        return False

    for i in range(clen - qlen + 1):
        if list(candidate_tokens[i:i + qlen]) == list(query_tokens):
            return True
    return False


def has_token_prefix_match(query_tokens: Sequence[str], candidate_tokens: Sequence[str], min_prefix: int = 3) -> bool:
    """
    Allows prefix matching at token boundaries.
    Example:
      query: ["cut"]
      candidate: ["cutout", "top"]
      -> True

    But:
      query: ["lion"]
      candidate: ["medallion"]
      -> False
    """
    if not query_tokens or not candidate_tokens:
        return False
    if len(query_tokens) != 1:
        return False

    q = query_tokens[0]
    if len(q) < min_prefix:
        return False

    for tok in candidate_tokens:
        if tok.startswith(q):
            return True
    return False

def score_single_match(
    query_text: str,
    query_norm: str,
    query_base: str,
    query_tokens: List[str],
    query_base_tokens: List[str],
    field_value: IndexedFieldValue,
    field_weight: float,
    match_case: bool,
) -> Optional[MatchEvidence]:
    if field_weight <= 0:
        return None

    original = field_value.original
    candidate_norm = field_value.normalized
    candidate_base = phrase_from_tokens(field_value.base_tokens)

    score = 0.0
    reasons: List[str] = []

    # --------------------------------------------------------
    # Literal-first pass in match-case mode
    # --------------------------------------------------------
    if match_case:
        literal_query = query_text.strip()
        literal_candidate = original

        if literal_query and literal_candidate == literal_query:
            score += field_weight * 1.55
            reasons.append("literal exact match")

        if score == 0.0:
            if query_norm and candidate_norm == query_norm:
                score += field_weight * 1.18
                reasons.append("normalized exact match")
            elif query_base and candidate_base == query_base:
                score += field_weight * 1.12
                reasons.append("base-form exact match")
            elif has_exact_token_match(query_base_tokens, field_value.base_tokens):
                score += field_weight * 0.98
                reasons.append("exact token match")
            elif has_token_sequence_match(query_base_tokens, field_value.base_tokens):
                score += field_weight * 0.90
                reasons.append("token sequence match")
            elif has_token_prefix_match(query_base_tokens, field_value.base_tokens):
                score += field_weight * 0.78
                reasons.append("token prefix match")
        else:
            # ----------------------------------------------------
            # Forgiving normalized pass
            # ----------------------------------------------------
            if query_norm and candidate_norm == query_norm:
                score += field_weight * 1.45
                reasons.append("normalized exact match")
            elif query_base and candidate_base == query_base:
                score += field_weight * 1.32
                reasons.append("base-form exact match")
            elif has_exact_token_match(query_base_tokens, field_value.base_tokens):
                score += field_weight * 1.12
                reasons.append("exact token match")
            elif has_token_sequence_match(query_base_tokens, field_value.base_tokens):
                score += field_weight * 1.00
                reasons.append("token sequence match")
            elif has_token_prefix_match(query_base_tokens, field_value.base_tokens):
                score += field_weight * 0.82
                reasons.append("token prefix match")
            

    # --------------------------------------------------------
    # Token-based reinforcement
    # --------------------------------------------------------
    overlap = token_overlap_ratio(query_base_tokens, field_value.base_tokens)
    if overlap > 0:
        if overlap == 1.0:
            score += field_weight * 0.35
            reasons.append("all query tokens matched")
        else:
            score += field_weight * (0.18 * overlap)
            reasons.append("partial token overlap")

    # --------------------------------------------------------
    # Extra key-specific bonuses
    # --------------------------------------------------------
    if field_value.field_name == "key":
        if not match_case:
            if candidate_norm == query_norm:
                score += 60.0
                reasons.append("key exact bonus")
            elif has_exact_token_match(query_base_tokens, field_value.base_tokens):
                score += 10.0
                reasons.append("key token bonus")
            elif has_token_sequence_match(query_base_tokens, field_value.base_tokens):
                score += 8.0
                reasons.append("key token sequence bonus")
            elif has_token_prefix_match(query_base_tokens, field_value.base_tokens):
                score += 6.0
                reasons.append("key token prefix bonus")
        else:
            if query_text.strip() == original:
                score += 60.0
                reasons.append("key literal exact bonus")
            elif has_exact_token_match(query_base_tokens, field_value.base_tokens):
                score += 10.0
                reasons.append("key token bonus")
            elif has_token_sequence_match(query_base_tokens, field_value.base_tokens):
                score += 8.0
                reasons.append("key token sequence bonus")
            elif has_token_prefix_match(query_base_tokens, field_value.base_tokens):
                score += 6.0
                reasons.append("key token prefix bonus")

    if score <= 0:
        return None

    return MatchEvidence(
        field_name=field_value.field_name,
        reason="; ".join(reasons),
        score=round(score, 3),
        matched_value=original,
    )


def search_index(
    index: List[IndexedEntry],
    query_text: str,
    options: SearchOptions,
    directives: AdvancedDirectives,
) -> Tuple[List[SearchResult], List[str]]:
    field_modes, effective_weights, warnings = resolve_field_modes(options, directives)

    query_norm = normalize_text(query_text)
    query_base = base_phrase(query_text)
    query_tokens = tokenize_text(query_text, keep_case=options.match_case)
    query_base_tokens = base_tokens(query_text)

    results: List[SearchResult] = []

    for entry in index:
        evidences: List[MatchEvidence] = []

        for field_value in entry.searchable_fields:
            field_name = field_value.field_name

            if field_modes.get(field_name) == "ignored":
                continue

            field_weight = effective_weights.get(field_name, DEFAULT_FIELD_WEIGHTS.get(field_name, 8.0))
            evidence = score_single_match(
                query_text=query_text,
                query_norm=query_norm,
                query_base=query_base,
                query_tokens=query_tokens,
                query_base_tokens=query_base_tokens,
                field_value=field_value,
                field_weight=field_weight,
                match_case=options.match_case,
            )
            if evidence is not None:
                evidences.append(evidence)

        if not evidences:
            continue

        # Aggregate result score.
        total_score = sum(ev.score for ev in evidences)

        # Reward diversity of useful matched fields, but lightly.
        unique_fields = sorted(set(ev.field_name for ev in evidences))
        total_score += len(unique_fields) * 2.5

        # Prefer entries whose strongest evidence is from key-ish identity fields.
        if "key" in unique_fields:
            total_score += 4.0
        if "entry.aliases" in unique_fields:
            total_score += 2.5

        # Sort evidences for readable output.
        evidences.sort(key=lambda e: e.score, reverse=True)

        definition = EntryDefinition(
            category=entry.category,
            key=entry.key,
            file=entry.file,
            meta=entry.meta,
            entry_fields=entry.entry_fields,
            extra_fields=entry.extra_fields,
        )

        results.append(
            SearchResult(
                category=entry.category,
                key=entry.key,
                file=entry.file,
                score=round(total_score, 3),
                display_text=format_prompt_token(entry.category, entry.key, options.display_format),
                matched_fields=unique_fields,
                reasons=[ev.reason for ev in evidences[:5]],
                evidences=evidences,
                definition=definition,
            )
        )

    results.sort(
        key=lambda r: (
            -r.score,
            r.category,
            r.key,
        )
    )

    return results[: options.max_results], warnings


# ============================================================
# Human / JSON Output
# ============================================================

def compact_list_preview(values: Any, limit: int = 3) -> str:
    items = safe_list_of_strings(values)
    if not items:
        return ""
    shown = items[:limit]
    suffix = " ..." if len(items) > limit else ""
    return "; ".join(shown) + suffix


def result_to_json_obj(result: SearchResult) -> Dict[str, Any]:
    return {
        "category": result.category,
        "key": result.key,
        "file": result.file,
        "score": result.score,
        "display_text": result.display_text,
        "matched_fields": result.matched_fields,
        "reasons": result.reasons,
        "evidences": [asdict(ev) for ev in result.evidences],
        "definition": {
            "category": result.definition.category,
            "key": result.definition.key,
            "file": result.definition.file,
            "meta": result.definition.meta,
            "entry_fields": result.definition.entry_fields,
            "extra_fields": result.definition.extra_fields,
        },
    }


def print_human_results(
    query_text: str,
    options: SearchOptions,
    directives: AdvancedDirectives,
    warnings: List[str],
    results: List[SearchResult],
) -> None:
    print(f"Query: {query_text}")
    print(f"Preset: {options.preset}")
    print(f"Display: {'category:key' if options.display_format == 'colon' else 'category=key'}")
    print(f"Match case: {'on' if options.match_case else 'off'}")

    if directives.raw_directives:
        print("Advanced directives:")
        for item in directives.raw_directives:
            print(f"  {item}")

    if warnings and options.show_warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"  {warning}")

    print()

    if not results:
        print("No results.")
        return

    for idx, result in enumerate(results, start=1):
        print(f"[{idx}] {result.display_text}")
        print(f"    score: {result.score}")
        print(f"    matched fields: {', '.join(result.matched_fields)}")
        if result.evidences:
            top = result.evidences[0]
            print(f"    reason: {top.reason}")
            print(f"    matched value: {top.matched_value}")

        # Show a compact preview of the entry definition.
        tags_preview = compact_list_preview(result.definition.entry_fields.get("tags", []))
        aliases_preview = compact_list_preview(result.definition.entry_fields.get("aliases", []))
        related_preview = compact_list_preview(result.definition.entry_fields.get("related", []))

        if tags_preview:
            print(f"    tags: {tags_preview}")
        if aliases_preview:
            print(f"    aliases: {aliases_preview}")
        if related_preview:
            print(f"    related: {related_preview}")

        if options.show_definitions:
            print("    definition:")
            print(f"      category: {result.definition.category}")
            print(f"      key: {result.definition.key}")
            print(f"      file: {result.definition.file}")

            if result.definition.entry_fields:
                for field_name, value in result.definition.entry_fields.items():
                    print(f"      {field_name}: {json.dumps(value, ensure_ascii=False)}")

            if result.definition.extra_fields:
                for field_name, value in result.definition.extra_fields.items():
                    print(f"      extra.{field_name}: {json.dumps(value, ensure_ascii=False)}")

        print()


def print_json_results(
    query_text: str,
    options: SearchOptions,
    directives: AdvancedDirectives,
    warnings: List[str],
    results: List[SearchResult],
) -> None:
    payload = {
        "query": query_text,
        "preset": options.preset,
        "display_format": options.display_format,
        "match_case": options.match_case,
        "advanced_directives": directives.raw_directives,
        "warnings": warnings,
        "results": [result_to_json_obj(r) for r in results],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


# ============================================================
# CLI Helpers
# ============================================================

def parse_field_mode_items(items: List[str]) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for item in items:
        if "=" not in item:
            continue
        field_name, mode = item.split("=", 1)
        field_name = field_name.strip()
        mode = mode.strip().lower()
        if field_name:
            parsed[field_name] = mode
    return parsed


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ranked search engine for Semantic Prompt pack entries."
    )
    parser.add_argument(
        "query",
        help='Search query, e.g. "cutouts" or "double cutouts rank key:2.0"',
    )
    parser.add_argument(
        "--packs-root",
        required=True,
        help="Root folder containing pack JSON files.",
    )
    parser.add_argument(
        "--format",
        dest="display_format",
        choices=["colon", "equals"],
        default="colon",
        help="Display result tokens as category:key or category=key.",
    )
    parser.add_argument(
        "--match-case",
        action="store_true",
        help="Use literal-first case/separator-sensitive matching, then normalized fallback.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=25,
        help="Maximum number of results to return.",
    )
    parser.add_argument(
        "--show-definitions",
        action="store_true",
        help="Show full definition payloads in human-readable output.",
    )
    parser.add_argument(
        "--preset",
        default="prompt",
        choices=sorted(PRESET_FIELD_MODES.keys()),
        help="Search field preset.",
    )
    parser.add_argument(
        "--field-mode",
        action="append",
        default=[],
        metavar="FIELD=MODE",
        help="Override a field mode. Example: --field-mode entry.tags=high",
    )
    parser.add_argument(
        "--advanced",
        action="store_true",
        help="Enable advanced query directives like: rank key:2.0 ignore meta.notes",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit JSON output instead of human-readable output.",
    )
    parser.add_argument(
        "--quiet-warnings",
        action="store_true",
        help="Suppress warning output.",
    )
    return parser


# ============================================================
# Main
# ============================================================

def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    packs_root = Path(args.packs_root).expanduser()
    if not packs_root.exists():
        print(f"Error: packs root does not exist: {packs_root}", file=sys.stderr)
        return 2

    options = SearchOptions(
        packs_root=packs_root,
        display_format=args.display_format,
        match_case=args.match_case,
        max_results=max(1, args.max_results),
        show_definitions=args.show_definitions,
        json_output=args.json_output,
        preset=args.preset,
        field_modes=parse_field_mode_items(args.field_mode),
        advanced=args.advanced,
        show_warnings=not args.quiet_warnings,
    )

    base_query, directives = parse_advanced_query(args.query, enabled=options.advanced)
    if not base_query:
        print("Error: query is empty after parsing advanced directives.", file=sys.stderr)
        return 2

    index = build_index(options.packs_root)
    results, warnings = search_index(index, base_query, options, directives)

    if options.json_output:
        print_json_results(base_query, options, directives, warnings, results)
    else:
        print_human_results(base_query, options, directives, warnings, results)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())