from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

# Reuse the same safe-ish denylist idea you already use :contentReference[oaicite:6]{index=6}
DEFAULT_SAFE_EXCLUDES: Set[str] = set([
    "fetish_ballgags","fetish_clothing","fetish_collars","fetish_ears","fetish_furniture",
    "fetish_leash","fetish_pony","fetish_shackles","fetish_shibari",
    "accessories_nsfw","lingerie","nudity","nsfw",
])

SPACE_RE = re.compile(r"\s+")
TOKEN_RE = re.compile(r"[a-z0-9_]+")

def norm(s: str) -> str:
    return SPACE_RE.sub(" ", (s or "")).strip()

def tokenize(s: str) -> List[str]:
    return TOKEN_RE.findall((s or "").lower())

@dataclass
class SuggestSettings:
    total: int = 8
    max_per_category: int = 2
    require_subject: bool = True
    subject_category: str = "subject"
    safe_mode: bool = True

    # Search behavior
    min_query_len: int = 2
    max_seed_categories: int = 6          # how many categories we seed from query matches
    related_hops: int = 1                 # 0 = none, 1 = direct related, 2 = related-of-related

    # Category bias
    include_min: List[str] = field(default_factory=list)
    include_any: List[str] = field(default_factory=list)

@dataclass
class SuggestResult:
    directive: str
    picks: List[Tuple[str, str]]
    debug: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

class PromptSuggester:
    """
    UI-first prompt suggestion engine.
    - load once (packs index + optional category graph)
    - suggest prompts quickly from a query
    """

    def __init__(
        self,
        packs_dir: Path,
        *,
        rng: Optional[random.Random] = None,
        category_graph: Optional[Any] = None,  # your future CategoryGraph object
    ):
        self.packs_dir = Path(packs_dir).resolve()
        self.rng = rng or random.Random()
        self.category_graph = category_graph

        # Core indices
        self.packs: Dict[str, List[str]] = {}          # category -> keys
        self.key_index: Dict[str, List[Tuple[str,str]]] = {}  # token -> [(category,key)]
        self._load()

    def _load(self) -> None:
        # This mirrors your scan_packs/load_pack behavior :contentReference[oaicite:7]{index=7}
        packs: Dict[str, List[str]] = {}
        for p in sorted(self.packs_dir.rglob("*.json")):
            try:
                import json
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue

            if not isinstance(data, dict):
                continue

            meta = data.get("_meta") or {}
            cat = meta.get("category") if isinstance(meta, dict) else None
            cat = norm(cat) if isinstance(cat, str) and cat.strip() else norm(p.stem)
            if not cat:
                continue

            keys: List[str] = []
            for k in data.keys():
                if k == "_meta" or (isinstance(k, str) and k.startswith("_")):
                    continue
                if isinstance(k, str):
                    k2 = norm(k)
                    if k2:
                        keys.append(k2)

            if not keys:
                continue

            packs.setdefault(cat, []).extend(keys)

        # de-dupe
        for cat, keys in list(packs.items()):
            seen = set()
            out = []
            for k in keys:
                if k not in seen:
                    out.append(k)
                    seen.add(k)
            packs[cat] = out

        self.packs = packs
        self._build_key_index()

    def _build_key_index(self) -> None:
        idx: Dict[str, List[Tuple[str,str]]] = {}
        for cat, keys in self.packs.items():
            for k in keys:
                for t in tokenize(k):
                    idx.setdefault(t, []).append((cat, k))
        self.key_index = idx

    def _format_directive(self, items: List[Tuple[str,str]]) -> str:
        # matches your existing output format :contentReference[oaicite:8]{index=8}
        return "%%{" + ", ".join(f"{c}={k}" for c, k in items) + "}%%"

    def _expand_related_categories(self, seed: Set[str], hops: int) -> Set[str]:
        if not self.category_graph or hops <= 0:
            return set(seed)

        out = set(seed)
        frontier = set(seed)

        for _ in range(hops):
            nxt = set()
            for c in frontier:
                # expected: graph.get_related(c) -> iterable[str]
                try:
                    rel = set(self.category_graph.get_related(c) or [])
                except Exception:
                    rel = set()
                for r in rel:
                    if r not in out:
                        nxt.add(r)
            out |= nxt
            frontier = nxt
            if not frontier:
                break
        return out

    def _safe_excludes(self, safe_mode: bool) -> Set[str]:
        # same “safe-ish” denylist approach you already use :contentReference[oaicite:9]{index=9}
        return set(DEFAULT_SAFE_EXCLUDES) if safe_mode else set()

    def _pick_unique(
        self,
        cat: str,
        used: Set[Tuple[str,str]],
        per_cat: Dict[str,int],
        max_per_category: int,
        exclude_cats: Set[str],
    ) -> Optional[Tuple[str,str]]:
        if cat in exclude_cats:
            return None
        if per_cat.get(cat, 0) >= max_per_category:
            return None
        keys = self.packs.get(cat) or []
        if not keys:
            return None

        # try a few times to avoid repeats
        for _ in range(150):
            k = self.rng.choice(keys)
            if (cat, k) not in used:
                used.add((cat, k))
                per_cat[cat] = per_cat.get(cat, 0) + 1
                return (cat, k)

        # fallback allow repeats
        k = self.rng.choice(keys)
        used.add((cat, k))
        per_cat[cat] = per_cat.get(cat, 0) + 1
        return (cat, k)

    def suggest(self, query: str, settings: Optional[SuggestSettings] = None) -> SuggestResult:
        settings = settings or SuggestSettings()
        q = norm(query).lower()

        debug: Dict[str, Any] = {"query": q}
        warnings: List[str] = []

        if len(q) < settings.min_query_len:
            warnings.append("Query too short; generating a general random prompt.")
            q_tokens = []
        else:
            q_tokens = tokenize(q)

        exclude_cats = self._safe_excludes(settings.safe_mode)

        # 1) Seed categories from query tokens by matching against key tokens
        seed_pairs: List[Tuple[str,str]] = []
        seed_cats: List[str] = []
        for t in q_tokens:
            seed_pairs.extend(self.key_index.get(t, []))

        # rank categories by frequency
        freq: Dict[str,int] = {}
        for cat, key in seed_pairs:
            if cat in exclude_cats:
                continue
            freq[cat] = freq.get(cat, 0) + 1

        seed_cats = [c for c, _ in sorted(freq.items(), key=lambda kv: kv[1], reverse=True)]
        seed_cats = seed_cats[: settings.max_seed_categories]

        debug["seed_categories"] = seed_cats
        debug["seed_matches_count"] = len(seed_pairs)

        # 2) Expand via related categories (if graph available)
        expanded = self._expand_related_categories(set(seed_cats), settings.related_hops)
        debug["expanded_categories"] = sorted(expanded)

        # 3) Build pools
        all_categories = [c for c in self.packs.keys() if c not in exclude_cats]
        if not all_categories:
            return SuggestResult(directive="%%{}%%", picks=[], debug=debug, warnings=["No categories available after excludes."])

        preferred_pool = []
        # user hint pool: expanded first, then include_any, then everything
        preferred_pool.extend([c for c in sorted(expanded) if c in self.packs and c not in exclude_cats])
        preferred_pool.extend([c for c in settings.include_any if c in self.packs and c not in exclude_cats and c not in preferred_pool])

        # 4) Pick items
        picks: List[Tuple[str,str]] = []
        used: Set[Tuple[str,str]] = set()
        per_cat: Dict[str,int] = {}

        def add(cat: str) -> None:
            nonlocal picks
            if len(picks) >= settings.total:
                return
            picked = self._pick_unique(cat, used, per_cat, settings.max_per_category, exclude_cats)
            if picked:
                picks.append(picked)

        # subject anchor
        if settings.require_subject and settings.subject_category in self.packs and settings.subject_category not in exclude_cats:
            add(settings.subject_category)

        # include-min
        for cat in settings.include_min:
            add(cat)

        # if query produced seed categories, try to pick from them early
        for cat in seed_cats:
            add(cat)

        # fill remainder
        attempts = 0
        while len(picks) < settings.total and attempts < 25000:
            attempts += 1
            pool = preferred_pool if preferred_pool else all_categories
            cat = self.rng.choice(pool)
            add(cat)

            # stop if everything capped
            if attempts % 2000 == 0:
                any_pickable = any(per_cat.get(c, 0) < settings.max_per_category for c in all_categories)
                if not any_pickable:
                    break

        if not seed_cats and q_tokens:
            warnings.append("No matches found for query; generated a general random prompt.")

        directive = self._format_directive(picks)
        debug["excluded_categories"] = sorted(exclude_cats)
        return SuggestResult(directive=directive, picks=picks, debug=debug, warnings=warnings)