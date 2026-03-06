from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable
from typing import Iterable, Union

from semantic.tools.meta_backfill import MetaBackfillTool, BackfillFieldSpec  # from the tool we designed

TOKEN_RE = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*", re.I)

STOPWORDS = {
    "a","an","and","the","or","of","to","in","on","with","for","from",
    "style","styles","quality","good","best","high","low","detail","detailed",
    "skin","girl","boy","man","woman",  # you may want to tweak these
}

def _norm(s: str) -> str:
    return (s or "").strip()

def _tokens(text: str) -> List[str]:
    return [t.lower() for t in TOKEN_RE.findall(text or "")]

def _split_category_segments(cat: str) -> List[str]:
    # supports dot categories; if old categories exist, still works.
    parts = [p.strip().lower() for p in (cat or "").split(".") if p.strip()]
    return parts

def _as_list_str(x: Any) -> List[str]:
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

def _safe_add(score_map: Dict[str, float], term: str, score: float) -> None:
    term = term.strip().lower()
    if not term:
        return
    if term in STOPWORDS:
        return
    # avoid tiny tokens
    if len(term) <= 2:
        return
    score_map[term] = score_map.get(term, 0.0) + score

def _dedupe_preserve_rank(scored: List[Tuple[str, float]], limit: int) -> List[str]:
    # sorted by score desc, tie by alpha for stability
    scored = sorted(scored, key=lambda x: (-x[1], x[0]))
    out = []
    seen = set()
    for term, _ in scored:
        if term in seen:
            continue
        seen.add(term)
        out.append(term)
        if len(out) >= limit:
            break
    return out


@dataclass
class SuggestTagSettings:
    min_tags: int = 10
    max_tags: int = 25

    # weighting
    w_category_segment: float = 4.0
    w_title_token: float = 3.5
    w_meta_alias: float = 3.0
    w_related_cat_segment: float = 2.0

    w_entry_key: float = 2.5
    w_entry_alias: float = 2.0
    w_entry_tag_token: float = 1.0

    # include phrases (simple bigrams) from tags like "bikini top"
    include_bigrams: bool = True
    w_bigram: float = 1.2

    # cap how many entry tags to scan per entry (keeps it fast)
    max_entry_tags_scan: int = 60


@dataclass
class FileSuggestion:
    path: Path
    category: str
    suggested_search_tags: List[str]
    debug_top_scored: List[Tuple[str, float]] = field(default_factory=list)


class SearchTagSuggester:
    """
    UI-first suggester:
      - suggest_search_tags_for_file(path) -> FileSuggestion
      - suggest_for_folder(root) -> list[FileSuggestion]
    """

    def __init__(self, packs_root: Union[Path, str, Iterable[Union[Path, str]]]):
        # Allow a single path or a list/tuple of paths
        if isinstance(packs_root, (list, tuple, set)):
            roots = list(packs_root)
        else:
            roots = [packs_root]

        self.packs_roots: List[Path] = []
        for r in roots:
            p = Path(r).expanduser().resolve()
            if p.exists() and p.is_dir():
                self.packs_roots.append(p)

        if not self.packs_roots:
            raise ValueError(f"No valid packs_root directories provided: {packs_root!r}")


    def _read_json(self, p: Path) -> Dict[str, Any]:
        return json.loads(p.read_text(encoding="utf-8"))

    def suggest_search_tags_for_file(
        self,
        path: Path,
        settings: Optional[SuggestTagSettings] = None,
    ) -> Optional[FileSuggestion]:
        settings = settings or SuggestTagSettings()
        path = Path(path)

        try:
            data = self._read_json(path)
        except Exception:
            return None
        if not isinstance(data, dict):
            return None

        meta = data.get("_meta") if isinstance(data.get("_meta"), dict) else {}
        cat = _norm(meta.get("category", "")) if isinstance(meta, dict) else ""
        if not cat:
            # fall back to filename
            cat = path.stem

        score_map: Dict[str, float] = {}

        # 1) Category segments (dot taxonomy)
        for seg in _split_category_segments(cat):
            _safe_add(score_map, seg, settings.w_category_segment)

        # 2) Title tokens
        title = meta.get("title") if isinstance(meta, dict) else None
        if isinstance(title, str) and title.strip():
            for t in _tokens(title):
                _safe_add(score_map, t, settings.w_title_token)

        # 3) Meta aliases
        for a in _as_list_str(meta.get("aliases") if isinstance(meta, dict) else None):
            # allow alias phrases by tokenizing
            for t in _tokens(a):
                _safe_add(score_map, t, settings.w_meta_alias)

        # 4) Related categories: use their segments as hints
        for rc in _as_list_str(meta.get("related_categories") if isinstance(meta, dict) else None):
            for seg in _split_category_segments(rc):
                _safe_add(score_map, seg, settings.w_related_cat_segment)

        # 5) Entries: keys + aliases + tag tokens
        for key, entry in data.items():
            if not isinstance(key, str) or key.startswith("_"):
                continue
            if not isinstance(entry, dict):
                continue

            # entry key
            for t in _tokens(key):
                _safe_add(score_map, t, settings.w_entry_key)

            # entry aliases
            aliases = entry.get("aliases")
            if isinstance(aliases, list):
                for a in aliases:
                    if isinstance(a, str):
                        for t in _tokens(a):
                            _safe_add(score_map, t, settings.w_entry_alias)

            # entry tags
            tags = entry.get("tags")
            if isinstance(tags, list):
                scanned = 0
                for tag in tags:
                    if not isinstance(tag, str):
                        continue
                    scanned += 1
                    if scanned > settings.max_entry_tags_scan:
                        break
                    toks = _tokens(tag)
                    for t in toks:
                        _safe_add(score_map, t, settings.w_entry_tag_token)

                    # optional bigrams for phrases like "bikini top"
                    if settings.include_bigrams and len(toks) >= 2:
                        for i in range(len(toks) - 1):
                            bigram = f"{toks[i]} {toks[i+1]}"
                            _safe_add(score_map, bigram, settings.w_bigram)

        scored = list(score_map.items())
        # Choose a target length based on how much signal we have
        target = max(settings.min_tags, min(settings.max_tags, len(scored)))
        suggested = _dedupe_preserve_rank(scored, limit=target)

        # Keep some debug for UI “why these”
        debug_top = sorted(scored, key=lambda x: -x[1])[:40]

        return FileSuggestion(
            path=path,
            category=cat,
            suggested_search_tags=suggested,
            debug_top_scored=debug_top,
        )

    def suggest_for_folder(
        self,
        root: Union[Path, str, Iterable[Union[Path, str]], None] = None,
        settings: Optional[SuggestTagSettings] = None,
    ) -> List[FileSuggestion]:

        if root is None:
            roots = self.packs_roots
        elif isinstance(root, (list, tuple, set)):
            roots = [Path(r).expanduser().resolve() for r in root]
        else:
            roots = [Path(root).expanduser().resolve()]

        out: List[FileSuggestion] = []
        for r in roots:
            if not r.exists() or not r.is_dir():
                continue
            for fp in sorted(r.rglob("*.json")):
                if not fp.is_file():
                    continue
                sug = self.suggest_search_tags_for_file(fp, settings=settings)
                if sug:
                    out.append(sug)
        return out


# ---- Bridge: build a backfill plan + apply after UI approval ----

def build_search_tags_backfill_plan(
    packs_root: Path,
    suggestions: List[FileSuggestion],
    *,
    field_name: str = "search_tags",
    overwrite_existing: bool = False,
) -> Tuple[MetaBackfillTool, Any]:
    """
    Returns (tool, plan). The UI can show the plan and then apply it.
    """

    # We’ll generate values by looking up the suggestion for that file.
    sug_map = {s.path.resolve(): s for s in suggestions}

    def generator(fp: Path, data: Dict[str, Any], meta: Dict[str, Any]) -> Any:
        s = sug_map.get(fp.resolve())
        return s.suggested_search_tags if s else []

    tool = MetaBackfillTool(packs_root=packs_root)

    specs = [
        BackfillFieldSpec(
            name=field_name,
            field_type="list[str]",
            default=[],
            generator=generator,
            overwrite_existing=overwrite_existing,
            required=False,
        )
    ]

    plan = tool.build_plan(specs)
    return tool, plan