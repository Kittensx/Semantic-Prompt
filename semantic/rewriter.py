import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
import random

from .loaders import registry, category_meta_db


# Matches %% ... %% blocks (non-greedy)
RE_BLOCK = re.compile(r"%%(.*?)%%", re.DOTALL)

# Optional directive header inside a block:
# %%{medium=watercolor, lighting=neon} a rainy street%%
RE_DIRECTIVE = re.compile(r"^\s*\{([^}]*)\}\s*(.*)$", re.DOTALL)


@dataclass
class RewriteSettings:
    enabled_categories: Optional[List[str]] = None  # None => all discovered categories
    inject_negatives: bool = True
    strict: bool = False  # if True: only directives, no trigger matching
    keep_original_if_no_change: bool = True
    # in RewriteSettings
    cross_expansion_mode: str = "inline"  # "bucket" (current) or "inline"

    # output ordering
    category_order: List[str] = field(default_factory=lambda: [
        "subject", "lora", "medium", "composition", "lighting", "palette", "quality"
    ])

    # If True, add the raw sentence words as tags too (usually False)
    include_raw_sentence_tokens: bool = False
    apply_excludes: bool = False  # NEW
    randomize_category_order: bool = False  # NEW
    


@dataclass
class RewriteResult:
    rewritten_prompt: str
    negative_additions: List[str] = field(default_factory=list)
    debug: Dict[str, Any] = field(default_factory=dict)


def _split_directives(directive_text: str) -> Dict[str, List[str]]:
    """
    Parse directives into multi-value dict.

    Supports:
      {subject=1girl, subject=beach, lighting=neon}
    Returns:
      {"subject": ["1girl", "beach"], "lighting": ["neon"]}
    """
    out: Dict[str, List[str]] = {}
    if not (directive_text or "").strip():
        return out

    parts = [p.strip() for p in directive_text.split(",")]
    for p in parts:
        if not p:
            continue
        if "=" not in p:
            continue

        k, v = p.split("=", 1)
        k = k.strip().lower()
        # normalize "+=" into "+", so "negative+=" becomes "negative+"
        if k.endswith("+="):
            k = k[:-2] + "+"
        v = v.strip()
        if not k or not v:
            continue

        # Allow multiple values in one directive using | or ;
        vals = []
        for chunk in re.split(r"[|;]", v):
            chunk = chunk.strip()
            if chunk:
                vals.append(chunk)

        if not vals:
            continue

        out.setdefault(k, []).extend(vals)

    return out


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        x2 = x.strip()
        if not x2:
            continue
        if x2.lower() in seen:
            continue
        seen.add(x2.lower())
        out.append(x2)
    return out


def _category_enabled(category: str, settings: RewriteSettings) -> bool:
    if settings.enabled_categories is None:
        return True
    return category in settings.enabled_categories


def _canon_part(part: str) -> str:
    p = (part or "").strip().lower()
    if p.endswith("ies") and len(p) > 3:
        return p[:-3] + "y"
    if p.endswith("s") and not p.endswith("ss") and len(p) > 3:
        return p[:-1]
    return p


def _parts_equal(a: str, b: str) -> bool:
    return _canon_part(a) == _canon_part(b)


def _cat_parts(cat: str) -> List[str]:
    return [part for part in (cat or "").strip().lower().split(".") if part]


def _shorthand_score(query_parts: List[str], candidate_parts: List[str]) -> int:
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


def _resolve_category_ref(category_ref: str, enabled_categories: Optional[List[str]] = None) -> str:
    """
    Resolve a category reference used by directives or requires.

    Supports:
      - exact dotted categories
      - shorthand dotted refs like: skirts.length
      - simple plural/singular tolerance: skirt.length -> ...skirts.mod.length
      - cat_id references: cat_ab12cd34ef56

    Returns the best resolved category if found; otherwise returns the
    original reference unchanged.
    """
    ref = (category_ref or "").strip().lower()
    if not ref:
        return ""

    if ref.startswith("cat_"):
        try:
            resolved = category_meta_db.get_category(ref)
            if isinstance(resolved, str) and resolved.strip():
                return resolved.strip().lower()
        except Exception:
            return ref

    available = enabled_categories or registry.get_categories() or []
    available_norm: List[str] = []
    seen = set()
    for cat in available:
        c = (cat or "").strip().lower()
        if c and c not in seen:
            available_norm.append(c)
            seen.add(c)

    if ref in seen:
        return ref

    query_parts = _cat_parts(ref)
    scored: List[Tuple[int, str]] = []
    for cat in available_norm:
        score = _shorthand_score(query_parts, _cat_parts(cat))
        if score >= 0:
            scored.append((score, cat))

    if not scored:
        return ref

    best_score = max(score for score, _ in scored)
    best_matches = sorted(cat for score, cat in scored if score == best_score)
    return best_matches[0] if best_matches else ref


def _resolve_required_category_ref(category_ref: str, enabled_categories: Optional[List[str]] = None) -> str:
    """
    Resolve a requires-category reference.

    Supports:
      - dotted category ids: appearance.makeup.lipstick.mod.color
      - legacy underscore categories: palette_colors
      - cat_id references: cat_ab12cd34ef56

    Returns the resolved category string if possible, otherwise returns the
    original reference unchanged so legacy/non-DB categories still work.
    """
    ref = (category_ref or "").strip().lower()
    if not ref:
        return ""

    if ref.startswith("cat_"):
        try:
            resolved = category_meta_db.get_category(ref)
            if isinstance(resolved, str) and resolved.strip():
                return resolved.strip().lower()
        except Exception:
            return ref

    return ref


def _apply_pack_entry(category: str, key: str, tags_out: Dict[str, List[str]], neg_out: List[str], debug: Dict, settings: RewriteSettings, enabled_categories: Optional[List[str]] = None, _stack=None, ):
    if _stack is None:
        _stack = set()

    # Prevent infinite loops: (category,key) already expanding
    stack_key = (category, key.lower())
    if stack_key in _stack:
        debug.setdefault("requires_cycle", []).append(stack_key)
        return
    _stack.add(stack_key)

    entry = registry.get_pack(category, key)
    if not entry:
        debug.setdefault("missing_pack_entries", []).append((category, key))
        _stack.remove(stack_key)
        return

    # Standard fields
    tags = entry.get("tags") or []
    if isinstance(tags, list):
        tags_out.setdefault(category, []).extend(tags)

    # Cross-category expansions (optional)
    for cross_cat in ("subject", "medium", "composition", "lighting", "palette", "quality", "style"):
        cross = entry.get(cross_cat)
        if isinstance(cross, list):           
            target_cat = cross_cat if settings.cross_expansion_mode == "bucket" else category
            tags_out.setdefault(target_cat, []).extend(cross)

    neg = entry.get("negative") or []
    if settings.inject_negatives and isinstance(neg, list):
        neg_out.extend(neg)

    # NEW: excludes (store them for later filtering)    
    raw_excludes = entry.get("excludes", [])
    ex_list = []

    if isinstance(raw_excludes, str):
        ex_list = [raw_excludes.strip().lower()] if raw_excludes.strip() else []
    elif isinstance(raw_excludes, list):
        ex_list = [x.strip().lower() for x in raw_excludes if isinstance(x, str) and x.strip()]

    if ex_list:
        tags_out.setdefault("__excludes__", []).extend(ex_list)
        debug.setdefault("excludes_seen", []).append((category, key, ex_list))

    

    # NEW: requires (apply additional pack entries)
    requires = entry.get("requires")
    if isinstance(requires, list):
        req_items = [x.strip() for x in requires if isinstance(x, str) and x.strip()]
        if req_items:
            debug.setdefault("requires_seen", []).append((category, key, req_items))

        for req in req_items:
            # Allow "<category_or_cat_id>:<key>" format, else same category.
            # Dotted categories work as-is. cat_id references are resolved
            # through category_meta_db when possible.
            if ":" in req:
                req_cat, req_key = req.split(":", 1)
                req_cat = _resolve_required_category_ref(req_cat, enabled_categories=enabled_categories)
                req_key = req_key.strip().lower()
                if req_cat and req_key:
                    _apply_pack_entry(req_cat, req_key, tags_out, neg_out, debug, settings=settings, enabled_categories=enabled_categories, _stack=_stack)
            else:
                _apply_pack_entry(category, req.lower(), tags_out, neg_out, debug, settings=settings, enabled_categories=enabled_categories, _stack=_stack)

    _stack.remove(stack_key)

def _parse_tag_weight(s: str) -> tuple[str, str | None]:
    """
    Accepts:
      "beach:1.2" -> ("beach", "1.2")
      "beach"     -> ("beach", None)
    Only splits on the LAST ":" so tags like "foo:bar:1.1" still work.
    """
    s = (s or "").strip()
    if not s:
        return "", None
    if ":" not in s:
        return s, None
    left, right = s.rsplit(":", 1)
    left = left.strip()
    right = right.strip()
    if not left or not right:
        return s, None
    # simple weight validation
    try:
        float(right)
    except Exception:
        return s, None
    return left, right

def _resolve_compound_value(raw: str, enabled_categories: List[str]) -> List[Tuple[str, str]]:
    """
    Greedy longest-match scan over tokens to find pack keys across enabled categories.
    Returns list of (category, key) to apply in order.
    Unknown tokens are returned as ("__literal__", token).
    """
    s = (raw or "").strip().lower()
    if not s:
        return []

    # tokenize (keep it simple for v0)
    tokens = re.findall(r"[a-z0-9_]+", s)
    if not tokens:
        return [("__literal__", s)]

    results: List[Tuple[str, str]] = []
    i = 0

    # Build a quick lookup: key -> list[categories it exists in]
    # (registry.packs already stores category->key->entry)
    key_to_cats: Dict[str, List[str]] = {}
    for cat in enabled_categories:
        for k in registry.packs.get(cat, {}).keys():
            key_to_cats.setdefault(k, []).append(cat)

    while i < len(tokens):
        matched = False

        # longest phrase first
        for j in range(len(tokens), i, -1):
            phrase = " ".join(tokens[i:j])
            cats = key_to_cats.get(phrase)
            if cats:
                # If a phrase exists in multiple categories, prefer the first
                # enabled category order as given.
                chosen_cat = None
                for c in enabled_categories:
                    if c in cats:
                        chosen_cat = c
                        break
                if chosen_cat is None:
                    chosen_cat = cats[0]

                results.append((chosen_cat, phrase))
                i = j
                matched = True
                break

        if not matched:
            # literal fallback token
            results.append(("__literal__", tokens[i]))
            i += 1

    return results
def rewrite_text_block(block_text: str, settings: RewriteSettings) -> Tuple[str, List[str], Dict]:
    """
    Rewrites only the content inside a single %%...%% block.
    Returns: (rewritten_fragment, negative_additions, debug)
    """
    debug: Dict[str, Any] = {"original_block": block_text}

    directives: Dict[str, List[str]] = {}
    sentence = block_text

    m = RE_DIRECTIVE.match(block_text)
    if m:
        directives = _split_directives(m.group(1))
        sentence = m.group(2) or ""
        debug["directives"] = directives

    tags_by_cat: Dict[str, List[str]] = {}
    neg_additions: List[str] = []

    # Decide enabled categories set (used for compound fallback resolution)
    enabled_categories = settings.enabled_categories
    if enabled_categories is None:
        enabled_categories = registry.get_categories()

    # 1) Directives override: {medium=watercolor, lighting=neon}
    for cat, keys in directives.items():
        cat = _resolve_category_ref((cat or "").strip().lower(), enabled_categories=enabled_categories)
        if not cat:
            continue

        # Normalize keys to a list[str]
        if isinstance(keys, str):
            keys = [keys]
        elif not isinstance(keys, list):
            continue

        # Special directive categories
        if cat in ("neg", "negative", "neg+", "negative+"):
            for raw in keys:
                raw = (raw or "").strip()
                if not raw:
                    continue
                tag, wt = _parse_tag_weight(raw)
                if not tag:
                    continue
                neg_additions.append(f"({tag}:{wt})" if wt else tag)
            debug.setdefault("directive_negatives", []).extend(keys)
            continue

        if not _category_enabled(cat, settings):
            continue
        debug.setdefault("resolved_directive_categories", []).append(cat)

        if cat == "lora":
            for raw in keys:
                raw = (raw or "").strip()
                if not raw:
                    continue
                key, wt = _parse_tag_weight(raw)
                if not key:
                    continue
                strength = wt or "1.0"
                tags_by_cat.setdefault("lora", []).append(f"<lora:{key}:{strength}>")
            debug.setdefault("literal_loras", []).extend(keys)
            continue

        for raw in keys:
            raw = (raw or "").strip()
            if not raw:
                continue

            key, wt = _parse_tag_weight(raw)
            key_lc = (key or "").strip().lower()
            if not key_lc:
                continue

            # If pack entry exists, apply it
            if registry.get_pack(cat, key_lc):
                _apply_pack_entry(cat, key_lc, tags_by_cat, neg_additions, debug, settings=settings, enabled_categories=enabled_categories)

                # Optional: also include the literal directive token with weight (your existing behavior)
                if wt:
                    tags_by_cat.setdefault(cat, []).append(f"({key}:{wt})")
                    debug.setdefault("weighted_directives", []).append((cat, raw))
            else:
                # Compound / compositional parsing fallback
                resolved = _resolve_compound_value(key, enabled_categories)

                for rcat, rkey in resolved:
                    if rcat == "__literal__":
                        tags_by_cat.setdefault(cat, []).append(f"({rkey}:{wt})" if wt else rkey)
                    else:
                        _apply_pack_entry(rcat, rkey, tags_by_cat, neg_additions, debug, settings=settings, enabled_categories=enabled_categories)

                debug.setdefault("compound_directives", []).append((cat, key, resolved))

    # 2) Trigger matching (unless strict)
    if not settings.strict:
        trigger_matches = registry.find_triggers(sentence)
        debug["triggers"] = list(trigger_matches.keys())

        best_pick: Dict[str, Tuple[int, str]] = {}  # category -> (priority, key)

        for phrase, mapping in trigger_matches.items():
            if not isinstance(mapping, dict):
                continue

            for cat, rule in mapping.items():
                cat = (cat or "").strip().lower()
                if not cat:
                    continue
                if not _category_enabled(cat, settings):
                    continue
                if not isinstance(rule, dict):
                    continue

                # pick
                if "pick" in rule:
                    key = rule["pick"]
                    pr = int(rule.get("priority", 0))
                    if isinstance(key, str):
                        existing = best_pick.get(cat)
                        if existing is None or pr > existing[0]:
                            best_pick[cat] = (pr, key)

                # add
                if "add" in rule:
                    add_list = rule["add"]
                    if isinstance(add_list, str):
                        add_list = [add_list]
                    if isinstance(add_list, list):
                        for k in add_list:
                            if isinstance(k, str) and k.strip():
                                _apply_pack_entry(cat, k.strip(), tags_by_cat, neg_additions, debug, settings=settings, enabled_categories=enabled_categories)

        # Apply best picks after adds
        for cat, (pr, key) in best_pick.items():
            _apply_pack_entry(cat, key, tags_by_cat, neg_additions, debug, settings=settings, enabled_categories=enabled_categories)

    # Optional: include raw sentence tokens as tags
    if settings.include_raw_sentence_tokens:
        words = re.findall(r"[a-zA-Z0-9_']{3,}", sentence)
        if words:
            tags_by_cat.setdefault("subject", []).extend(words)

    # Build ordered output
    out_tags: List[str] = []

    order = list(settings.category_order or [])
    if settings.randomize_category_order:
        random.shuffle(order)

    for cat in order:
        if cat.startswith("__"):
            continue
        if not _category_enabled(cat, settings):
            continue
        tags = tags_by_cat.get(cat)
        if tags:
            out_tags.extend(tags)

    # Append any categories not mentioned in the order (stable dict order)
    for cat, tags in tags_by_cat.items():
        if cat.startswith("__"):
            continue
        if cat in order:
            continue
        if not _category_enabled(cat, settings):
            continue
        if tags:
            out_tags.extend(tags)

    # Excludes: apply only if enabled (collected by _apply_pack_entry into "__excludes__")
    excludes = set(tags_by_cat.get("__excludes__", []))
    if settings.apply_excludes and excludes:
        out_tags = [t for t in out_tags if t.strip().lower() not in excludes]
        debug["excludes_applied"] = sorted(excludes)

    # If there is trailing text inside the block, preserve it as a literal chunk at the end
    sentence = (sentence or "").strip()
    if sentence:
        out_tags.append(sentence)

    # Keep original block if nothing was produced
    if not out_tags and settings.keep_original_if_no_change:
        debug["kept_original_block"] = True
        return block_text, neg_additions, debug

    rewritten_fragment = ", ".join(out_tags).strip()
    debug["rewritten_fragment"] = rewritten_fragment
    debug["neg_additions"] = list(neg_additions)

    return rewritten_fragment, neg_additions, debug


def rewrite_prompt(prompt: str, settings: Optional[RewriteSettings] = None) -> RewriteResult:
    """
    Rewrites a full prompt string by expanding only %%...%% blocks.
    Returns rewritten prompt plus negative additions.
    """
    if settings is None:
        settings = RewriteSettings()

    debug: Dict[str, Any] = {"blocks": []}
    negative_additions: List[str] = []

    def repl(m: re.Match) -> str:
        block = m.group(1) or ""
        rewritten, negs, dbg = rewrite_text_block(block, settings)
        debug["blocks"].append(dbg)
        negative_additions.extend(negs)
        # Replace the whole %%...%% with the rewritten fragment
        return rewritten

    rewritten_prompt = RE_BLOCK.sub(repl, prompt)
    negative_additions = _dedupe_preserve_order(negative_additions)

    return RewriteResult(
        rewritten_prompt=rewritten_prompt,
        negative_additions=negative_additions,
        debug=debug
    )