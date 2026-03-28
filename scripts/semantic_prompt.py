import gradio as gr
from modules import scripts
import json
import os
import re
from pathlib import Path
from datetime import datetime

from semantic.rewriter import rewrite_prompt, RewriteSettings
from semantic.loaders import registry
from semantic.panels.registry import build_all
from semantic.panels.registry import get_panels
from semantic.discovery import discover_everything
from semantic.loaders import BASE_DIR, PACKS_DIRS, PANELS_DIRS, TOOLS_DIRS, ADDONS_DIR, TRIGGERS_DIRS
from modules import script_callbacks
from semantic.semantic_ui import build_semantic_ui

_PROMPT_COMPS = {"txt2img": None, "img2img": None}

def _on_after_component(component, **kwargs):
    elem_id = kwargs.get("elem_id")
    if elem_id == "txt2img_prompt":
        _PROMPT_COMPS["txt2img"] = component
    elif elem_id == "img2img_prompt":
        _PROMPT_COMPS["img2img"] = component

script_callbacks.on_after_component(_on_after_component)



_RE_BLOCK = re.compile(r"%%(.*?)%%", re.DOTALL)
_RE_DIRECTIVES = re.compile(r"^\s*\{([^}]*)\}", re.DOTALL)

def _norm_token(s: str) -> str:
    s = (s or "").strip().lower()

    # treat spaces, underscores, and hyphens the same
    s = re.sub(r"[\s_\-]+", "_", s)

    return s

def _extract_directive_pairs(prompt_text: str) -> list[tuple[str, str]]:
    """
    Returns ordered (category, key) pairs found in directive headers inside %%...%% blocks.
    Example: %%{subject=1girl|beach, appearance=blue eyes}%% -> [("subject","1girl"),("subject","beach"),("appearance","blue_eyes")]
    """
    out: list[tuple[str, str]] = []
    if not prompt_text:
        return out

    for m in _RE_BLOCK.finditer(prompt_text):
        inner = m.group(1) or ""
        dm = _RE_DIRECTIVES.match(inner)
        if not dm:
            continue

        directive_text = dm.group(1) or ""
        parts = [p.strip() for p in directive_text.split(",") if p.strip()]

        for part in parts:
            if "=" not in part:
                continue
            cat, val = part.split("=", 1)
            cat = _norm_token(cat)

            # ignore negative directives for ordering
            if cat.startswith("negative"):
                continue

            # support multiple values: a|b|c
            vals = [v.strip() for v in val.split("|") if v.strip()]
            for v in vals:
                out.append((cat, _norm_token(v)))

    return out

def _extract_used_categories(prompt_text: str) -> list[str]:
    pairs = _extract_directive_pairs(prompt_text)
    seen = set()
    out = []
    for cat, _key in pairs:
        if cat not in seen:
            seen.add(cat)
            out.append(cat)
    return out

def _priority_to_categories(priority_lines: list[str]) -> list[str]:
    """
    Accepts lines like 'subject', 'subject.1girl', 'lighting.theater.overhead'
    and returns ordered unique categories: ['subject','lighting',...]
    """
    seen = set()
    out = []
    for line in priority_lines:
        t = _norm_token(line)
        if not t:
            continue
        cat = t.split(".", 1)[0]
        if cat and cat not in seen:
            seen.add(cat)
            out.append(cat)
    return out

def _build_order_from_prompt(prompt_text: str, priority_lines: list[str], known_categories: list[str]) -> tuple[list[str], list[str]]:
    """
    Returns (category_order, detected_items_for_display)
    detected items are like ['subject.1girl','appearance.blue_eyes',...]
    """
    pairs = _extract_directive_pairs(prompt_text)
    detected_items = [f"{c}.{k}" for (c, k) in pairs]

    used_cats = _extract_used_categories(prompt_text)
    prio_cats = _priority_to_categories(priority_lines)

    # order = priority cats first (if used), then remaining used cats
    used_set = set(used_cats)
    out = []
    seen = set()

    for c in prio_cats:
        if c in used_set and c in known_categories and c not in seen:
            out.append(c)
            seen.add(c)

    for c in used_cats:
        if c in known_categories and c not in seen:
            out.append(c)
            seen.add(c)

    # if prompt has no directives, fall back to known_categories (or your default)
    if not out:
        out = known_categories[:]

    return out, detected_items
def container_builder_for_source(source):
    def builder(title, build_fn):
        panel_items = []
        for p in get_panels():
            if p.source != source:
                continue
            with gr.Tab(p.title):
                items = p.build_fn() or []
                panel_items.extend(items)
        return panel_items
    return builder
    
def _ext_root_dir() -> Path:
    # scripts/semantic_prompt.py -> scripts -> extension root
    return Path(__file__).resolve().parent.parent

def _packs_dir() -> Path:
    return _ext_root_dir() / "semantic" / "packs"

def _pack_file_for_category(category: str) -> Path:
    # Convention: category file is "<category>.json"
    return _packs_dir() / f"{category}.json"

def _load_pack_file(path: Path) -> dict:
    if not path.exists():
        return {"_meta": {"category": path.stem}}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _write_pack_file(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _backup_file(path: Path) -> Path:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    bak = path.with_suffix(path.suffix + f".bak_{ts}")
    if path.exists():
        bak.write_bytes(path.read_bytes())
    return bak

def _lines_to_list(s: str) -> list:
    out = []
    for line in (s or "").splitlines():
        t = line.strip()
        if not t:
            continue
        out.append(t)
    return out

def _list_to_lines(items) -> str:
    if not items:
        return ""
    if isinstance(items, list):
        return "\n".join(str(x) for x in items if str(x).strip())
    return ""

def _get_entry_keys(category: str) -> list:
    cat = (category or "").strip().lower()
    static = set((registry.packs.get(cat) or {}).keys())
    dynamic = set((registry.dynamic.get(cat) or {}).keys())
    return sorted(static | dynamic)

def _parse_category_order(order_text: str, known_categories: list[str]) -> list[str]:
    raw = (order_text or "").strip()
    if not raw:
        return known_categories[:]

    parts = [x.strip().lower() for x in raw.split(",") if x.strip()]

    out = []
    seen = set()

    # Add categories the user explicitly listed (if valid)
    for c in parts:
        if c in known_categories and c not in seen:
            out.append(c)
            seen.add(c)

    # Append any categories not mentioned
    for c in known_categories:
        if c not in seen:
            out.append(c)

    return out
    
def _default_category_order(known_categories: list[str]) -> list[str]:
    known = [c.lower() for c in (known_categories or [])]

    canonical = ["subject", "lora", "medium", "composition", "lighting", "palette", "quality"]

    # extras = anything in packs that isn't in canonical, minus subject
    extras = [c for c in known if c not in canonical and c != "subject"]

    out = ["subject"] + extras

    # append canonical (excluding subject because we already placed it)
    out += [c for c in canonical if c != "subject" and c in known]

    # finally, append anything we somehow missed (safety)
    seen = set(out)
    out += [c for c in known if c not in seen]
    return out
    
def _split_csv_tokens(s: str) -> list[str]:
    # simple comma-split; keeps behavior consistent with how A1111 treats negatives
    if not s:
        return []
    return [t.strip() for t in s.split(",") if t.strip()]

def _dedupe_tokens(tokens: list[str]) -> list[str]:
    seen = set()
    out = []
    for t in tokens:
        k = t.strip().lower()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(t.strip())
    return out

def _merge_negatives(base_neg: str, additions: list[str]) -> str:
    base_tokens = _split_csv_tokens(base_neg)
    add_tokens = [a.strip() for a in (additions or []) if a and a.strip()]
    merged = _dedupe_tokens(base_tokens + add_tokens)
    return ", ".join(merged)
    
def _append_unique_pack_negatives(base_neg: str, additions: list[str], seen_pack: set[str]) -> str:
    if not additions:
        return base_neg
    to_add = []
    for a in additions:
        if not a:
            continue
        t = a.strip()
        if not t:
            continue
        k = t.lower()
        if k in seen_pack:
            continue
        seen_pack.add(k)
        to_add.append(t)

    if not to_add:
        return base_neg

    if base_neg.strip():
        return base_neg.rstrip() + ", " + ", ".join(to_add)
    return ", ".join(to_add)
     

   
class SemanticPromptScript(scripts.Script):

    def title(self):
        return "Semantic Prompt (%%...%%)"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
       

        return build_semantic_ui(
            is_img2img=is_img2img,
            prompt_comps=_PROMPT_COMPS,
            build_order_from_prompt=_build_order_from_prompt,
            default_category_order=_default_category_order,
            lines_to_list=_lines_to_list,
            list_to_lines=_list_to_lines,
            get_entry_keys=_get_entry_keys,
            pack_file_for_category=_pack_file_for_category,
            load_pack_file=_load_pack_file,
            write_pack_file=_write_pack_file,
            backup_file=_backup_file,
        )   
    def _ensure_extra_params(self, p):
        if not hasattr(p, "extra_generation_params") or p.extra_generation_params is None:
            p.extra_generation_params = {}

    def _debug_record(self, p, stage: str, prompt_in: str, prompt_out: str, neg_in: str, neg_out: str):
        self._ensure_extra_params(p)

        def _short(s: str, n=240):
            s = s or ""
            s = s.replace("\n", " ")
            return s[:n]

        p.extra_generation_params[f"SemanticPrompt {stage} prompt_in"] = _short(prompt_in)
        p.extra_generation_params[f"SemanticPrompt {stage} prompt_out"] = _short(prompt_out)
        p.extra_generation_params[f"SemanticPrompt {stage} neg_in"] = _short(neg_in)
        p.extra_generation_params[f"SemanticPrompt {stage} neg_out"] = _short(neg_out)

        print(f"[SemanticPrompt] stage={stage}")
        print(f"  prompt_in : {_short(prompt_in)}")
        print(f"  prompt_out: {_short(prompt_out)}")
        print(f"  neg_in    : {_short(neg_in)}")
        print(f"  neg_out   : {_short(neg_out)}")

    def _apply_semantic_rewrite(
        self,
        p,
        stage: str,
        enabled, inject_negatives, strict, include_raw, cross_expansion_mode, keep_original_if_no_change, apply_excludes,  debug, order_from_prompt,
        order_text, use_default_order, randomize_order,
        *args
    ):
        if not enabled:
            return
        do_debug = bool(debug) and bool(strict)
        

        prompt_in = getattr(p, "prompt", "") or ""
        neg_in = getattr(p, "negative_prompt", "") or ""

        # ---- COPY of your existing before_process_batch logic START ----
        categories = sorted(registry.get_categories())
        category_values = list(args[:len(categories)])
        enabled_categories = [cat for cat, on in zip(categories, category_values) if on]

        settings = RewriteSettings(
            enabled_categories=enabled_categories,
            inject_negatives=bool(inject_negatives),
            strict=bool(strict),
            include_raw_sentence_tokens=bool(include_raw),
            cross_expansion_mode=("bucket" if bool(cross_expansion_mode) else "inline"),
            keep_original_if_no_change=bool(keep_original_if_no_change),
            apply_excludes=bool(apply_excludes)
        )

        known = [c.lower() for c in registry.get_categories()]
            
        # establish a base order (used if not deriving, or as a fallback)
        if use_default_order:
            settings.category_order = _default_category_order(known)
        else:
            settings.category_order = _parse_category_order(order_text, known)

        settings.randomize_category_order = bool(randomize_order)

        all_prompts = getattr(p, "all_prompts", None) or [getattr(p, "prompt", "")]
        all_negative_prompts = getattr(p, "all_negative_prompts", None)
        base_neg = getattr(p, "negative_prompt", "") or ""

        if not all_negative_prompts:
            all_negative_prompts = [base_neg] * len(all_prompts)
        else:
            all_negative_prompts = list(all_negative_prompts)
            if len(all_negative_prompts) < len(all_prompts):
                pad = all_negative_prompts[-1] if all_negative_prompts else base_neg
                all_negative_prompts.extend([pad] * (len(all_prompts) - len(all_negative_prompts)))
            elif len(all_negative_prompts) > len(all_prompts):
                all_negative_prompts = all_negative_prompts[:len(all_prompts)]

        if not all_prompts:
            all_prompts = [p.prompt]
            all_negative_prompts = [getattr(p, "negative_prompt", "")]

        new_prompts = []
        new_negs = []
        all_neg_additions = []

        for i, pr in enumerate(all_prompts):
            neg = all_negative_prompts[i] if all_negative_prompts and i < len(all_negative_prompts) else ""
            seen_pack_negs = set()
                
            if order_from_prompt:
                derived_order, _detected = _build_order_from_prompt(pr or "", [], known)
                settings.category_order = derived_order
            
            res = rewrite_prompt(pr, settings=settings)
            new_prompts.append(res.rewritten_prompt)

            # NEG blocks rewrite behavior (your current design)
            if "%%" in (neg or ""):
                from copy import copy
                neg_settings = copy(settings)
                neg_settings.inject_negatives = False
                neg_res = rewrite_prompt(neg, settings=neg_settings)
                neg = neg_res.rewritten_prompt

                if inject_negatives and neg_res.negative_additions:
                    neg = _append_unique_pack_negatives(neg, neg_res.negative_additions, seen_pack_negs)
                    all_neg_additions.extend(neg_res.negative_additions)

            if inject_negatives and res.negative_additions:
                neg = _append_unique_pack_negatives(neg, res.negative_additions, seen_pack_negs)
                all_neg_additions.extend(res.negative_additions)

            new_negs.append(neg)

        # Defensive assignment: set all common fields
        p.all_prompts = new_prompts
        p.all_negative_prompts = new_negs
        p.prompt = new_prompts[0]
        p.negative_prompt = new_negs[0]

        # Some builds also use p.prompts
        if hasattr(p, "prompts"):
            try:
                p.prompts = list(new_prompts)
            except Exception:
                pass

        # ---- COPY of your existing logic END ----

        prompt_out = getattr(p, "prompt", "") or ""
        neg_out = getattr(p, "negative_prompt", "") or ""

        # Record + print truth channels
        if do_debug:
            self._debug_record(p, stage, prompt_in, prompt_out, neg_in, neg_out)
        
        if do_debug: 
            # Keep your existing infotext flags too
            self._ensure_extra_params(p)
            p.extra_generation_params["SemanticPrompt"] = "enabled"
            p.extra_generation_params["SemanticPrompt strict"] = "1" if strict else "0"
            p.extra_generation_params["SemanticPrompt inject_negatives"] = "1" if inject_negatives else "0"
            p.extra_generation_params["SemanticPrompt enabled_categories"] = ", ".join(enabled_categories)

            if inject_negatives and all_neg_additions:
                uniq = []
                seen = set()
                for x in all_neg_additions:
                    xl = x.lower()
                    if xl in seen:
                        continue
                    seen.add(xl)
                    uniq.append(x)
                p.extra_generation_params["SemanticPrompt negatives_added"] = ", ".join(uniq)
    
    def before_process(self, p, *args, **kwargs):
        self._apply_semantic_rewrite(p, "before_process", *args)

    def process(self, p, *args, **kwargs):
        pass

    def before_process_batch(self, p, *args, **kwargs):
        # Important:
        # Rewrite the full semantic prompt set only once at job start.
        # Rewriting p.all_prompts again inside batch hooks can desync
        # prompt-conditioning shape from the current latent batch,
        # especially when batch_count (n_iter) > 1.
        
        pass
        