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
    s = re.sub(r"\s+", "_", s)
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
        categories = sorted(registry.get_categories())
        report = discover_everything(
            base_dir=BASE_DIR,
            packs_dirs=PACKS_DIRS,
            panels_dirs=PANELS_DIRS,
            tools_dirs=TOOLS_DIRS,
            addons_dir=ADDONS_DIR,
        )

        with gr.Accordion("Semantic Prompt (%%...%%) - sentence expansion", open=False):
            enabled = gr.Checkbox(value=True, label="Enable semantic rewrite (only inside %%...%%)")

            inject_negatives = gr.Checkbox(
                value=False,
                label="Append negatives from packs (e.g. watercolor -> photo, hyperrealistic)"
            )

            strict = gr.Checkbox(
                value=False,
                label="Strict mode: only apply explicit {category=value} directives, ignore keyword triggers"
            )

            include_raw = gr.Checkbox(
                value=False,
                label="Also include raw sentence words as tags (usually OFF)"
            )
            cross_expansion_mode = gr.Checkbox( 
                label="Bucket cross-category fields into their own categories (subject/lighting/palette/etc)",
                value=False
            )
            keep_original_if_no_change = gr.Checkbox(
                label="Keep original %%...%% block text if expansion produces no tags",
                value=True
            )
            apply_excludes = gr.Checkbox(
                label="Apply 'excludes' filtering (remove excluded tags from output)",
                value=False
            )
            
            debug = gr.Checkbox(
                value=False,
                label="Debug (strict only): write prompt_in/out to infotext + print stages"
            )
           
            
            
            # Tips for markdown
            gr.Markdown(
                "Tip: Inline directives inside a block are supported.\n\n"
                "Examples:\n"
                "- Multiple subjects: `%%{subject=1girl|beach, medium=watercolor, lighting=neon, palette=muted} a rainy street%%`\n"
                "- Weighted tags: `%%{subject=beach:1.2, lighting=neon:1.1} ... %%`\n"
                "- Add negatives: `%%{negative+=blurry|lowres|jpeg artifacts} ... %%`"
            )
            
            # ----------------------------
            # Preview section
            # ----------------------------
            gr.Markdown("### Preview (no generation)")
            preview_in = gr.Textbox(
                label="Preview input prompt (leave blank to use current prompt)",
                lines=3,
                placeholder="Example: portrait, %%a watercolor valley at dusk with rain%%, film grain"
            )

            preview_btn = gr.Button("Preview rewrite")

            preview_out_prompt = gr.Textbox(
                label="Rewritten prompt (what would be sent to the model)",
                lines=4
            )

            preview_out_negs = gr.Textbox(
                label="Negatives to add (if enabled)",
                lines=2
            )

            preview_out_debug = gr.Textbox(
                label="Debug (triggers matched per %%...%% block)",
                lines=8
            )
            panel_items = []

            with gr.Accordion("Panels", open=False):
                with gr.Tabs():
                    with gr.Tab("Core"):
                        panel_items += build_all(container_builder_for_source("core"))
                    with gr.Tab("Patches"):
                        panel_items += build_all(container_builder_for_source("patch"))
                    with gr.Tab("User"):
                        panel_items += build_all(container_builder_for_source("user"))
                        
            with gr.Accordion("Categories", open=False):
                order_from_prompt = gr.Checkbox(
                    value=False,
                    label="During generation: derive category order from directives in the prompt"
                )
                cats_lower = [c.lower() for c in registry.get_categories()]
                default_order = _default_category_order(cats_lower)


                order_text = gr.Textbox(
                    label="Category order (comma-separated)",
                    value=", ".join(default_order),  # auto-populated from loaded packs
                    )
                reset_order_btn = gr.Button("Reset order to default")
                
                display_mode = gr.Radio(
                    choices=["All categories", "Used in prompt only"],
                    value="All categories",
                    label="Category display"
                )

                priority_text = gr.Textbox(
                    label="Priority (one per line, supports category or category.key)",
                    lines=4,
                    placeholder="subject.1girl\nappearance.blue_eyes\nlighting.theater.theater_overhead"
                )

                
                prompt_comp = _PROMPT_COMPS["img2img"] if is_img2img else _PROMPT_COMPS["txt2img"]

                def _refresh_from_prompt(main_prompt_text: str, preview_text: str, mode: str, priority_lines: str):
                    cats2 = [c.lower() for c in registry.get_categories()]
                    prio = _lines_to_list(priority_lines)
                    prompt_text = (main_prompt_text or "").strip() or (preview_text or "").strip()

                    order, detected = _build_order_from_prompt(prompt_text or "", prio, cats2)

                    # update category checkbox visibility if "used only"
                    used_set = set(order) if mode == "Used in prompt only" else None
                    cat_updates = []
                    for c in categories:
                        if used_set is None:
                            cat_updates.append(gr.update(visible=True))
                        else:
                            cat_updates.append(gr.update(visible=(c.lower() in used_set)))

                    md = "Detected from prompt: " + (", ".join(detected) if detected else "(none)")
                    return (
                        gr.update(value=", ".join(order)),
                        gr.update(value=md),
                        *cat_updates
                    )
                #Detect Prompts from text and show category order
                detected_md = gr.Markdown(value="Detected from prompt: (none)")
                

                def _reset_order():
                    cats2 = [c.lower() for c in registry.get_categories()]
                    return ", ".join(_default_category_order(cats2))

                reset_order_btn.click(fn=_reset_order, inputs=[], outputs=[order_text])
                

                fill_order_btn = gr.Button("Order grouping by all categories")
                def _fill_order():
                    # re-pull in case you have a reload button that updates registry
                    cats2 = [c.lower() for c in registry.get_categories()]
                    return gr.update(value=", ".join(cats2))
                refresh_from_prompt_btn = gr.Button("Refresh from prompt window")
                fill_order_btn.click(fn=_fill_order, inputs=[], outputs=[order_text])
                randomize_order = gr.Checkbox(value=False, label="Randomize category order each iteration")
            
                use_default_order = gr.Checkbox(
                    value=True,
                    label="Use default order (subject, extras, then canonical list)"
                )
                def _toggle_order_box(use_default):
                    return gr.update(interactive=not use_default)

                use_default_order.change(fn=_toggle_order_box, inputs=[use_default_order], outputs=[order_text])

                gr.Markdown("### Categories to apply (auto-detected from packs)")
                category_checks = []
                default_on = {c: (c != "quality") for c in categories}

                with gr.Row():
                    for c in categories:
                        category_checks.append(gr.Checkbox(value=default_on.get(c, True), label=c))
                refresh_inputs = [prompt_comp, display_mode, priority_text] if prompt_comp is not None else [preview_in, display_mode, priority_text]
                refresh_outputs = [order_text, detected_md] + category_checks
                
                refresh_from_prompt_btn.click(
                    fn=_refresh_from_prompt,
                    inputs=[prompt_comp, preview_in, display_mode, priority_text],
                    outputs=[order_text, detected_md] + category_checks
                )
            # ----------------------------
            # Live Pack Editor
            # ----------------------------
            with gr.Accordion("Edit Packs (live)", open=False):
                gr.Markdown(
                    "Edit the JSON packs on disk while A1111 is running. "
                    "Saves create a timestamped .bak backup automatically."
                )

                cat_choices = sorted(registry.get_categories())
                edit_category = gr.Dropdown(
                    choices=cat_choices,
                    value=cat_choices[0] if cat_choices else None,
                    label="Category"
                )

                edit_key = gr.Dropdown(
                    choices=_get_entry_keys(cat_choices[0]) if cat_choices else [],
                    value=None,
                    label="Entry key"
                )

                new_key = gr.Textbox(
                    label="New key (for Create / Save As)",
                    placeholder="e.g., rainy street"
                )

                tags_box = gr.Textbox(label="tags (one per line)", lines=6)
                negative_box = gr.Textbox(label="negative (one per line)", lines=4)

                # Optional cross-category fields
                lighting_box = gr.Textbox(label="lighting (one per line)", lines=3)
                palette_box = gr.Textbox(label="palette (one per line)", lines=3)
                composition_box = gr.Textbox(label="composition (one per line)", lines=3)
                quality_box = gr.Textbox(label="quality (one per line)", lines=3)
                style_box = gr.Textbox(label="style (one per line)", lines=3)

                with gr.Row():
                    load_btn = gr.Button("Load")
                    save_btn = gr.Button("Save (overwrite)")
                    save_as_btn = gr.Button("Save As (new key)")
                with gr.Row():
                    confirm_delete = gr.Checkbox(value=False, label="I understand delete is permanent")
                    delete_btn = gr.Button("Delete")

                edit_status = gr.Textbox(label="Status", lines=2)
    
        saved_key_state = gr.State(value="")
        ui_items = [enabled, inject_negatives, strict, include_raw, cross_expansion_mode, keep_original_if_no_change, apply_excludes,  debug,  order_from_prompt, order_text, use_default_order, randomize_order] + category_checks + [
            preview_in, preview_btn, preview_out_prompt, preview_out_negs, preview_out_debug,
            edit_category, edit_key, new_key,
            tags_box, negative_box, lighting_box, palette_box, composition_box, quality_box, style_box,
            load_btn, save_btn, save_as_btn, confirm_delete, delete_btn, edit_status, saved_key_state] + panel_items
        
        
        
       
        
        
        
        
        # Wire preview button
        def _preview(preview_text, enabled_val, inject_negs_val, strict_val, include_raw_val, cross_bucket_val, keep_original_val, apply_excludes_val, debug_val, *cat_vals):
            # Preview should work even if the main toggle is off.
            # We'll just note it in debug so it's clear preview != generation.
            
            note = ""
            if not enabled_val:
                note = "Note: Semantic rewrite is OFF for generation right now; this is preview only.\n\n"

            # If user leaves preview box empty, don't guess; tell them to paste something.
            if not (preview_text or "").strip():
                return "", "", "Paste a prompt into Preview input, then click Preview rewrite."
        
        

            enabled_categories = [cat for cat, on in zip(categories, cat_vals) if on]

            settings = RewriteSettings(
                enabled_categories=enabled_categories,
                inject_negatives=bool(inject_negs_val),
                strict=bool(strict_val),
                include_raw_sentence_tokens=bool(include_raw_val),
                cross_expansion_mode=("bucket" if bool(cross_bucket_val) else "inline"),
                keep_original_if_no_change=bool(keep_original_val),
                apply_excludes=bool(apply_excludes_val)
            )

            res = rewrite_prompt(preview_text, settings=settings)

            negs = ", ".join(res.negative_additions) if (inject_negs_val and res.negative_additions) else ""

            # Build readable debug output
            dbg_lines = []
            blocks = res.debug.get("blocks", [])
            for idx, b in enumerate(blocks, start=1):
                orig = (b.get("original_block") or "").strip().replace("\n", " ")
                directives = b.get("directives", {})
                triggers = b.get("triggers", [])
                rewritten = (b.get("rewritten_fragment") or "").strip()

                dbg_lines.append(f"Block #{idx}:")
                dbg_lines.append(f"  original: {orig}")
                if directives:
                    dbg_lines.append(f"  directives: {directives}")
                dbg_lines.append(f"  triggers: {triggers}")
                dbg_lines.append(f"  rewritten: {rewritten}")
                missing = b.get("missing_pack_entries")
                if missing:
                    dbg_lines.append(f"  missing_pack_entries: {missing}")
                dbg_lines.append("")

            if debug_val:
                # show full block breakdown
                debug_text = note + "\n".join(dbg_lines).strip()
            else:
                debug_text = ""
            return res.rewritten_prompt, negs, debug_text

        

        preview_btn.click(
            fn=_preview,
            inputs=[preview_in, enabled, inject_negatives, strict, include_raw, cross_expansion_mode, keep_original_if_no_change, apply_excludes, debug] + category_checks,
            outputs=[preview_out_prompt, preview_out_negs, preview_out_debug]
            )
            
        # Build return list (must include everything you created!)
        
        # ----------------------------
        # Live Pack Editor wiring
        # ----------------------------
        def _refresh_keys_for_category(category: str):
            category = (category or "").strip()
            if not category:
                return gr.update(choices=[], value=None)

            keys = _get_entry_keys(category)
            return gr.update(choices=keys, value=(keys[0] if keys else None))

        def _load_entry(category: str, key: str):
            category = (category or "").strip()
            key = (key or "").strip().lower()
            if not category or not key:
                return "", "", "", "", "", "", "", "Select a category and key, then click Load."

            entry = registry.get_pack(category, key)
            if not entry or entry.get("_dynamic"):
                # blank template for first-time edits
                return ("", "", "", "", "", "", "", f"New entry template: {category}/{key}")

            return (
                _list_to_lines(entry.get("tags")),
                _list_to_lines(entry.get("negative")),
                _list_to_lines(entry.get("lighting")),
                _list_to_lines(entry.get("palette")),
                _list_to_lines(entry.get("composition")),
                _list_to_lines(entry.get("quality")),
                _list_to_lines(entry.get("style")),
                f"Loaded {category}/{key}"
            )

        def _save_entry(category: str, key: str, tags, neg, lighting, palette, composition, quality, style):
            category = (category or "").strip()
            key = (key or "").strip().lower()
            if not category or not key:
                return "Select a category and key to Save."

            path = _pack_file_for_category(category)
            data = _load_pack_file(path)

            meta = data.get("_meta") or {}
            meta.setdefault("category", category)
            data["_meta"] = meta

            entry = {}

            tag_list = _lines_to_list(tags)
            if tag_list:
                entry["tags"] = tag_list

            neg_list = _lines_to_list(neg)
            if neg_list:
                entry["negative"] = neg_list

            for fname, box in (
                ("lighting", lighting),
                ("palette", palette),
                ("composition", composition),
                ("quality", quality),
                ("style", style),
            ):
                lst = _lines_to_list(box)
                if lst:
                    entry[fname] = lst

            _backup_file(path)
            data[key] = entry
            _write_pack_file(path, data)

            registry.reload_all()
            return f"Saved {category}/{key} (backup created).", key

        def _save_as(category: str, new_key_value: str, tags, neg, lighting, palette, composition, quality, style):
            category = (category or "").strip()
            new_key_value = (new_key_value or "").strip().lower()
            if not category or not new_key_value:
                return "Provide Category + New key, then click Save As."

            return _save_entry(category, new_key_value, tags, neg, lighting, palette, composition, quality, style)
            

        def _delete_entry(category: str, key: str, ok: bool):
            category = (category or "").strip()
            key = (key or "").strip().lower()
            if not ok:
                return "Check the confirmation box to enable Delete."
            if not category or not key:
                return "Select a category and key to Delete."

            path = _pack_file_for_category(category)
            data = _load_pack_file(path)

            if key not in data:
                return f"Key not found in file: {key}"

            _backup_file(path)
            del data[key]
            _write_pack_file(path, data)

            registry.reload_all()
            return f"Deleted {category}/{key} (backup created)."
        edit_key.change(
            fn=_load_entry,
            inputs=[edit_category, edit_key],
            outputs=[tags_box, negative_box, lighting_box, palette_box, composition_box, quality_box, style_box, edit_status]
        )
        edit_category.change(
            fn=_refresh_keys_for_category,
            inputs=[edit_category],
            outputs=[edit_key]
        ).then(
            fn=_load_entry,
            inputs=[edit_category, edit_key],
            outputs=[tags_box, negative_box, lighting_box, palette_box, composition_box, quality_box, style_box, edit_status]
        )

        load_btn.click(
            fn=_load_entry,
            inputs=[edit_category, edit_key],
            outputs=[tags_box, negative_box, lighting_box, palette_box, composition_box, quality_box, style_box, edit_status]
        )

        save_btn.click(
            fn=_save_entry,
            inputs=[edit_category, edit_key, tags_box, negative_box, lighting_box, palette_box, composition_box, quality_box, style_box],
            outputs=[edit_status, saved_key_state]
        ).then(
            fn=_refresh_keys_for_category,
            inputs=[edit_category],
            outputs=[edit_key]
        ).then(
            fn=lambda k: gr.update(value=k),
            inputs=[saved_key_state],
            outputs=[edit_key]
        ).then(
            fn=_load_entry,
            inputs=[edit_category, edit_key],
            outputs=[tags_box, negative_box, lighting_box, palette_box, composition_box, quality_box, style_box, edit_status]
        )

        save_as_btn.click(
            fn=_save_as,
            inputs=[edit_category, new_key, tags_box, negative_box, lighting_box, palette_box, composition_box, quality_box, style_box],
            outputs=[edit_status, saved_key_state]
        ).then(
            fn=_refresh_keys_for_category,
            inputs=[edit_category],
            outputs=[edit_key]
        ).then(
            fn=lambda k: gr.update(value=k),
            inputs=[saved_key_state],
            outputs=[edit_key]
        ).then(
            fn=_load_entry,
            inputs=[edit_category, edit_key],
            outputs=[tags_box, negative_box, lighting_box, palette_box, composition_box, quality_box, style_box, edit_status]
        )

        delete_btn.click(
            fn=_delete_entry,
            inputs=[edit_category, edit_key, confirm_delete],
            outputs=[edit_status]
        ).then(
            fn=_refresh_keys_for_category,
            inputs=[edit_category],
            outputs=[edit_key]
        ).then(
            fn=_load_entry,
            inputs=[edit_category, edit_key],
            outputs=[tags_box, negative_box, lighting_box, palette_box, composition_box, quality_box, style_box, edit_status]
        )

        return ui_items

    

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
        self._apply_semantic_rewrite(p, "process", *args)

    def before_process_batch(self, p, *args, **kwargs):
        self._apply_semantic_rewrite(p, "before_process_batch", *args)
        
