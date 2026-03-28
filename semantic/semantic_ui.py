"""
Standalone UI builder for Semantic Prompt.

Expected usage from the main script class:

    def ui(self, is_img2img):
        try:
            from semantic.semantic_ui import build_semantic_ui
        except Exception:
            from semantic_ui import build_semantic_ui

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
"""

from __future__ import annotations

import gradio as gr
from typing import Any, Callable, Dict

try:
    from semantic.rewriter import rewrite_prompt, RewriteSettings
    from semantic.loaders import registry, PACKS_DIRS
except Exception:
    from rewriter import rewrite_prompt, RewriteSettings
    from loaders import registry, PACKS_DIRS


JsonDict = Dict[str, Any]


def _import_search_tag_suggester():
    last_error = None
    for module_name in (
        "semantic.tools.search_tag_suggester",
        "semantic.search_tag_suggester",
        "search_tag_suggester",
    ):
        try:
            module = __import__(module_name, fromlist=["SearchTagSuggester"])
            return getattr(module, "SearchTagSuggester")
        except Exception as e:
            last_error = e
    raise ImportError(f"Could not import SearchTagSuggester: {last_error!r}")

def _import_pack_search_engine():
    last_error = None
    for module_name in (
        "semantic.tools.pack_search_engine",
        "semantic.pack_search_engine",
        "pack_search_engine",
    ):
        try:
            module = __import__(module_name, fromlist=[
                "SearchOptions",
                "parse_advanced_query",
                "build_index",
                "search_index",
            ])
            return (
                getattr(module, "SearchOptions"),
                getattr(module, "parse_advanced_query"),
                getattr(module, "build_index"),
                getattr(module, "search_index"),
            )
        except Exception as e:
            last_error = e
    raise ImportError(f"Could not import pack_search_engine: {last_error!r}")

def _scan_search_tags(_query: str) -> JsonDict | list[JsonDict]:
    try:
        SearchTagSuggester = _import_search_tag_suggester()
    except Exception as e:
        return {"error": f"SearchTagSuggester import failed: {e!r}"}

    try:
        suggester = SearchTagSuggester(PACKS_DIRS)
        suggestions = suggester.suggest_for_folder()
        return [
            {
                "file": str(s.path),
                "category": s.category,
                "search_tags": list((s.suggested_search_tags or [])[:20]),
            }
            for s in (suggestions or [])[:50]
        ]
    except Exception as e:
        return {"error": repr(e)}


BuildOrderFn = Callable[[str, list[str], list[str]], tuple[list[str], list[str]]]
LinesToListFn = Callable[[str], list[str]]
ListToLinesFn = Callable[[Any], str]
GetEntryKeysFn = Callable[[str], list]
PackPathFn = Callable[[str], Any]
LoadPackFn = Callable[[Any], dict]
WritePackFn = Callable[[Any, dict], None]
BackupFileFn = Callable[[Any], Any]

def _pack_search(
    query: str,
    preset: str,
    display_format: str,
    max_results: int,
    match_case: bool,
    advanced: bool,
):
    query = (query or "").strip()
    if not query:
        return (
            gr.update(choices=[], value=None),
            [],
            "Enter a search query, then click Search.",
            "",
        )

    try:
        SearchOptions, parse_advanced_query, build_index, search_index = _import_pack_search_engine()
    except Exception as e:
        return (
            gr.update(choices=[], value=None),
            [],
            f"Pack search import failed: {e!r}",
            "",
        )

    try:
        packs_root = PACKS_DIRS[0]
    except Exception:
        return (
            gr.update(choices=[], value=None),
            [],
            "Could not determine PACKS_DIRS[0] for pack search.",
            "",
        )

    try:
        options = SearchOptions(
            packs_root=packs_root,
            display_format=display_format,
            match_case=bool(match_case),
            max_results=max(1, int(max_results or 25)),
            preset=preset,
            advanced=bool(advanced),
            show_warnings=True,
        )

        base_query, directives = parse_advanced_query(query, enabled=options.advanced)
        if not base_query:
            return (
                gr.update(choices=[], value=None),
                [],
                "Query is empty after parsing advanced directives.",
                "",
            )

        index = build_index(options.packs_root)
        results, warnings = search_index(index, base_query, options, directives)

        result_payloads = []
        choices = []
        for r in results:
            label = f"{r.display_text}  |  score={r.score}"
            result_payloads.append(
                {
                    "label": label,
                    "display_text": r.display_text,
                    "category": r.category,
                    "key": r.key,
                    "score": r.score,
                    "file": r.file,
                    "matched_fields": r.matched_fields,
                    "reasons": r.reasons,
                    "definition": {
                        "meta": r.definition.meta,
                        "entry_fields": r.definition.entry_fields,
                        "extra_fields": r.definition.extra_fields,
                    },
                }
            )
            choices.append(label)

        status_lines = [
            f"Query: {base_query}",
            f"Preset: {preset}",
            f"Results: {len(result_payloads)}",
        ]
        if directives.raw_directives:
            status_lines.append("Directives: " + ", ".join(directives.raw_directives))
        if warnings:
            status_lines.append("Warnings: " + " | ".join(warnings))

        first_detail = ""
        if result_payloads:
            first_detail = _format_pack_result_detail(result_payloads[0])

        return (
            gr.update(choices=choices, value=(choices[0] if choices else None)),
            result_payloads,
            "\n".join(status_lines),
            first_detail,
        )

    except Exception as e:
        return (
            gr.update(choices=[], value=None),
            [],
            f"Pack search failed: {e!r}",
            "",
        )


def _format_pack_result_detail(item: dict) -> str:
    if not item:
        return ""

    definition = item.get("definition") or {}
    meta = definition.get("meta") or {}
    entry_fields = definition.get("entry_fields") or {}
    extra_fields = definition.get("extra_fields") or {}

    lines = [
        f"Token: {item.get('display_text', '')}",
        f"Category: {item.get('category', '')}",
        f"Key: {item.get('key', '')}",
        f"Score: {item.get('score', '')}",
        f"Matched fields: {', '.join(item.get('matched_fields') or [])}",
        f"Reasons: {' | '.join(item.get('reasons') or [])}",
        f"File: {item.get('file', '')}",
        "",
    ]

    title = meta.get("title")
    notes = meta.get("notes")
    if title:
        lines.append(f"Meta title: {title}")
    if notes:
        lines.append(f"Meta notes: {notes}")

    for field_name in ("tags", "aliases", "related", "requires", "excludes", "negative"):
        value = entry_fields.get(field_name)
        if value:
            if isinstance(value, list):
                lines.append(f"{field_name}: " + "; ".join(str(v) for v in value))
            else:
                lines.append(f"{field_name}: {value}")

    if extra_fields:
        lines.append("")
        lines.append("Extra fields:")
        for k, v in extra_fields.items():
            if isinstance(v, list):
                lines.append(f"  {k}: " + "; ".join(str(x) for x in v))
            else:
                lines.append(f"  {k}: {v}")

    return "\n".join(lines)


def _select_pack_result(selected_label: str, result_payloads: list[dict]):
    if not selected_label or not result_payloads:
        return "", ""

    for item in result_payloads:
        if item.get("label") == selected_label:
            return item.get("display_text", ""), _format_pack_result_detail(item)

    return "", ""


def _append_token(existing_text: str, token: str) -> str:
    existing_text = existing_text or ""
    token = (token or "").strip()
    if not token:
        return existing_text

    if not existing_text.strip():
        return token

    if existing_text.rstrip().endswith(","):
        return existing_text.rstrip() + " " + token

    return existing_text.rstrip() + ", " + token
    
def build_semantic_ui(
    *,
    is_img2img: bool,
    prompt_comps: dict,
    build_order_from_prompt: BuildOrderFn,
    default_category_order: Callable[[list[str]], list[str]],
    lines_to_list: LinesToListFn,
    list_to_lines: ListToLinesFn,
    get_entry_keys: GetEntryKeysFn,
    pack_file_for_category: PackPathFn,
    load_pack_file: LoadPackFn,
    write_pack_file: WritePackFn,
    backup_file: BackupFileFn,
):
    categories = sorted(registry.get_categories())
    with gr.Accordion("Pack Search", open=False):
        gr.Markdown(
            "Search pack entries and insert a selected token into the preview box or prompt."
        )

        with gr.Row():
            pack_search_query = gr.Textbox(
                label="Search query",
                placeholder='Examples: double cutouts, open shoulder blouse, medallion',
                scale=6,
            )
            pack_search_btn = gr.Button("Search", scale=1)

        with gr.Row():
            pack_search_preset = gr.Dropdown(
                choices=["prompt", "exact_key", "broad", "relationships", "debug"],
                value="prompt",
                label="Preset",
            )
            pack_search_format = gr.Dropdown(
                choices=["colon", "equals"],
                value="colon",
                label="Token format",
            )
            pack_search_max = gr.Slider(
                minimum=1,
                maximum=100,
                value=25,
                step=1,
                label="Max results",
            )

        with gr.Row():
            pack_search_match_case = gr.Checkbox(
                value=False,
                label="Match case",
            )
            pack_search_advanced = gr.Checkbox(
                value=False,
                label="Advanced query syntax",
            )

        pack_search_status = gr.Textbox(
            label="Search status",
            lines=3,
        )

        pack_search_results_state = gr.State(value=[])
        selected_pack_token = gr.State(value="")

        pack_search_results = gr.Dropdown(
            choices=[],
            value=None,
            label="Results",
            interactive=True,
        )

        with gr.Row():
            insert_into_preview_btn = gr.Button("Insert into Preview input")
            insert_into_prompt_btn = gr.Button("Insert into Prompt")

        selected_token_box = gr.Textbox(
            label="Selected token",
            lines=1,
        )

        pack_result_detail = gr.Textbox(
            label="Selected result details",
            lines=14,
        )

    with gr.Accordion("Semantic Prompt (%%...%%) - sentence expansion", open=False):
        enabled = gr.Checkbox(value=True, label="Enable semantic rewrite (only inside %%...%%)")

        inject_negatives = gr.Checkbox(
            value=False,
            label="Append negatives from packs (e.g. watercolor -> photo, hyperrealistic)",
        )

        strict = gr.Checkbox(
            value=False,
            label="Strict mode: only apply explicit {category=value} directives, ignore keyword triggers",
        )

        include_raw = gr.Checkbox(
            value=False,
            label="Also include raw sentence words as tags (usually OFF)",
        )
        cross_expansion_mode = gr.Checkbox(
            label="Bucket cross-category fields into their own categories (subject/lighting/palette/etc)",
            value=False,
        )
        keep_original_if_no_change = gr.Checkbox(
            label="Keep original %%...%% block text if expansion produces no tags",
            value=True,
        )
        apply_excludes = gr.Checkbox(
            label="Apply 'excludes' filtering (remove excluded tags from output)",
            value=False,
        )

        debug = gr.Checkbox(
            value=False,
            label="Debug (strict only): write prompt_in/out to infotext + print stages",
        )

        gr.Markdown(
            "Tip: Inline directives inside a block are supported.\n\n"
            "Examples:\n"
            "- Multiple subjects: `%%{subject=1girl|beach, medium=watercolor, lighting=neon, palette=muted} a rainy street%%`\n"
            "- Weighted tags: `%%{subject=beach:1.2, lighting=neon:1.1} ... %%`\n"
            "- Add negatives: `%%{negative+=blurry|lowres|jpeg artifacts} ... %%`"
        )

        gr.Markdown("### Preview (no generation)")
        preview_in = gr.Textbox(
            label="Preview input prompt (leave blank to use current prompt)",
            lines=3,
            placeholder="Example: portrait, %%a watercolor valley at dusk with rain%%, film grain",
        )
        preview_btn = gr.Button("Preview rewrite")
        preview_out_prompt = gr.Textbox(
            label="Rewritten prompt (what would be sent to the model)",
            lines=4,
        )
        preview_out_negs = gr.Textbox(
            label="Negatives to add (if enabled)",
            lines=2,
        )
        preview_out_debug = gr.Textbox(
            label="Debug (triggers matched per %%...%% block)",
            lines=8,
        )

        with gr.Accordion("Categories", open=False):
            order_from_prompt = gr.Checkbox(
                value=False,
                label="During generation: derive category order from directives in the prompt",
            )
            cats_lower = [c.lower() for c in registry.get_categories()]
            default_order = default_category_order(cats_lower)

            order_text = gr.Textbox(
                label="Category order (comma-separated)",
                value=", ".join(default_order),
            )
            reset_order_btn = gr.Button("Reset order to default")

            display_mode = gr.Radio(
                choices=["All categories", "Used in prompt only"],
                value="All categories",
                label="Category display",
            )

            priority_text = gr.Textbox(
                label="Priority (one per line, supports category or category.key)",
                lines=4,
                placeholder="subject.1girl\nappearance.blue_eyes\nlighting.theater.theater_overhead",
            )

            prompt_comp = prompt_comps.get("img2img") if is_img2img else prompt_comps.get("txt2img")
            main_prompt_input = prompt_comp if prompt_comp is not None else gr.State(value="")

            def _refresh_from_prompt(main_prompt_text: str, preview_text: str, mode: str, priority_lines: str):
                cats2 = [c.lower() for c in registry.get_categories()]
                prio = lines_to_list(priority_lines)
                prompt_text = (main_prompt_text or "").strip() or (preview_text or "").strip()

                order, detected = build_order_from_prompt(prompt_text or "", prio, cats2)

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
                    *cat_updates,
                )

            detected_md = gr.Markdown(value="Detected from prompt: (none)")

            def _reset_order():
                cats2 = [c.lower() for c in registry.get_categories()]
                return ", ".join(default_category_order(cats2))

            reset_order_btn.click(fn=_reset_order, inputs=[], outputs=[order_text])

            fill_order_btn = gr.Button("Order grouping by all categories")

            def _fill_order():
                cats2 = [c.lower() for c in registry.get_categories()]
                return gr.update(value=", ".join(cats2))

            refresh_from_prompt_btn = gr.Button("Refresh from prompt window")
            fill_order_btn.click(fn=_fill_order, inputs=[], outputs=[order_text])

            randomize_order = gr.Checkbox(value=False, label="Randomize category order each iteration")
            use_default_order = gr.Checkbox(
                value=True,
                label="Use default order (subject, extras, then canonical list)",
            )

            def _toggle_order_box(use_default: bool):
                return gr.update(interactive=not use_default)

            use_default_order.change(fn=_toggle_order_box, inputs=[use_default_order], outputs=[order_text])

            gr.Markdown("### Categories to apply (auto-detected from packs)")
            category_checks = []
            default_on = {c: (c != "quality") for c in categories}

            with gr.Row():
                for c in categories:
                    category_checks.append(gr.Checkbox(value=default_on.get(c, True), label=c))

            refresh_from_prompt_btn.click(
                fn=_refresh_from_prompt,
                inputs=[main_prompt_input, preview_in, display_mode, priority_text],
                outputs=[order_text, detected_md] + category_checks,
            )
            
        with gr.Accordion("Search Tag Builder", open=False):
            gr.Markdown(
                "This is the existing search-tag panel moved into its own accordion. "
                "It is intentionally left as-is rather than being folded into the panel system."
            )
            search_tag_query = gr.Textbox(
                label="Scan packs for suggested search tags",
                placeholder="(no query needed) just scan",
            )
            search_tag_scan_btn = gr.Button("Scan")
            search_tag_out = gr.JSON(label="Suggestions (preview)")
            search_tag_scan_btn.click(
                fn=_scan_search_tags,
                inputs=[search_tag_query],
                outputs=[search_tag_out],
            )

        with gr.Accordion("Edit Packs (live)", open=False):
            gr.Markdown(
                "Edit the JSON packs on disk while A1111 is running. "
                "Saves create a timestamped .bak backup automatically."
            )

            cat_choices = sorted(registry.get_categories())
            edit_category = gr.Dropdown(
                choices=cat_choices,
                value=cat_choices[0] if cat_choices else None,
                label="Category",
            )
            edit_key = gr.Dropdown(
                choices=get_entry_keys(cat_choices[0]) if cat_choices else [],
                value=None,
                label="Entry key",
            )
            new_key = gr.Textbox(
                label="New key (for Create / Save As)",
                placeholder="e.g., rainy street",
            )

            tags_box = gr.Textbox(label="tags (one per line)", lines=6)
            negative_box = gr.Textbox(label="negative (one per line)", lines=4)
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

    def _preview(
        preview_text,
        enabled_val,
        inject_negs_val,
        strict_val,
        include_raw_val,
        cross_bucket_val,
        keep_original_val,
        apply_excludes_val,
        debug_val,
        *cat_vals,
    ):
        note = ""
        if not enabled_val:
            note = "Note: Semantic rewrite is OFF for generation right now; this is preview only.\n\n"

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
            apply_excludes=bool(apply_excludes_val),
        )

        res = rewrite_prompt(preview_text, settings=settings)
        negs = ", ".join(res.negative_additions) if (inject_negs_val and res.negative_additions) else ""

        dbg_lines = []
        blocks = res.debug.get("blocks", [])
        for idx, block in enumerate(blocks, start=1):
            orig = (block.get("original_block") or "").strip().replace("\n", " ")
            directives = block.get("directives", {})
            triggers = block.get("triggers", [])
            rewritten = (block.get("rewritten_fragment") or "").strip()

            dbg_lines.append(f"Block #{idx}:")
            dbg_lines.append(f"  original: {orig}")
            if directives:
                dbg_lines.append(f"  directives: {directives}")
            dbg_lines.append(f"  triggers: {triggers}")
            dbg_lines.append(f"  rewritten: {rewritten}")
            missing = block.get("missing_pack_entries")
            if missing:
                dbg_lines.append(f"  missing_pack_entries: {missing}")
            dbg_lines.append("")

        debug_text = note + "\n".join(dbg_lines).strip() if debug_val else ""
        return res.rewritten_prompt, negs, debug_text

    preview_btn.click(
        fn=_preview,
        inputs=[
            preview_in,
            enabled,
            inject_negatives,
            strict,
            include_raw,
            cross_expansion_mode,
            keep_original_if_no_change,
            apply_excludes,
            debug,
        ] + category_checks,
        outputs=[preview_out_prompt, preview_out_negs, preview_out_debug],
    )

    def _refresh_keys_for_category(category: str):
        category = (category or "").strip()
        if not category:
            return gr.update(choices=[], value=None)

        keys = get_entry_keys(category)
        return gr.update(choices=keys, value=(keys[0] if keys else None))

    def _load_entry(category: str, key: str):
        category = (category or "").strip()
        key = (key or "").strip().lower()
        if not category or not key:
            return "", "", "", "", "", "", "", "Select a category and key, then click Load."

        entry = registry.get_pack(category, key)
        if not entry or entry.get("_dynamic"):
            return ("", "", "", "", "", "", "", f"New entry template: {category}/{key}")

        return (
            list_to_lines(entry.get("tags")),
            list_to_lines(entry.get("negative")),
            list_to_lines(entry.get("lighting")),
            list_to_lines(entry.get("palette")),
            list_to_lines(entry.get("composition")),
            list_to_lines(entry.get("quality")),
            list_to_lines(entry.get("style")),
            f"Loaded {category}/{key}",
        )

    def _save_entry(category: str, key: str, tags, neg, lighting, palette, composition, quality, style):
        category = (category or "").strip()
        key = (key or "").strip().lower()
        if not category or not key:
            return "Select a category and key to Save.", ""

        path = pack_file_for_category(category)
        data = load_pack_file(path)

        meta = data.get("_meta") or {}
        meta.setdefault("category", category)
        data["_meta"] = meta

        entry = {}

        tag_list = lines_to_list(tags)
        if tag_list:
            entry["tags"] = tag_list

        neg_list = lines_to_list(neg)
        if neg_list:
            entry["negative"] = neg_list

        for fname, box in (
            ("lighting", lighting),
            ("palette", palette),
            ("composition", composition),
            ("quality", quality),
            ("style", style),
        ):
            lst = lines_to_list(box)
            if lst:
                entry[fname] = lst

        backup_file(path)
        data[key] = entry
        write_pack_file(path, data)

        registry.reload_all()
        return f"Saved {category}/{key} (backup created).", key

    def _save_as(category: str, new_key_value: str, tags, neg, lighting, palette, composition, quality, style):
        category = (category or "").strip()
        new_key_value = (new_key_value or "").strip().lower()
        if not category or not new_key_value:
            return "Provide Category + New key, then click Save As.", ""

        return _save_entry(category, new_key_value, tags, neg, lighting, palette, composition, quality, style)

    def _delete_entry(category: str, key: str, ok: bool):
        category = (category or "").strip()
        key = (key or "").strip().lower()
        if not ok:
            return "Check the confirmation box to enable Delete."
        if not category or not key:
            return "Select a category and key to Delete."

        path = pack_file_for_category(category)
        data = load_pack_file(path)
        if key not in data:
            return f"Key not found in file: {key}"

        backup_file(path)
        del data[key]
        write_pack_file(path, data)

        registry.reload_all()
        return f"Deleted {category}/{key} (backup created)."

    edit_key.change(
        fn=_load_entry,
        inputs=[edit_category, edit_key],
        outputs=[tags_box, negative_box, lighting_box, palette_box, composition_box, quality_box, style_box, edit_status],
    )
    edit_category.change(
        fn=_refresh_keys_for_category,
        inputs=[edit_category],
        outputs=[edit_key],
    ).then(
        fn=_load_entry,
        inputs=[edit_category, edit_key],
        outputs=[tags_box, negative_box, lighting_box, palette_box, composition_box, quality_box, style_box, edit_status],
    )

    load_btn.click(
        fn=_load_entry,
        inputs=[edit_category, edit_key],
        outputs=[tags_box, negative_box, lighting_box, palette_box, composition_box, quality_box, style_box, edit_status],
    )

    save_btn.click(
        fn=_save_entry,
        inputs=[edit_category, edit_key, tags_box, negative_box, lighting_box, palette_box, composition_box, quality_box, style_box],
        outputs=[edit_status, saved_key_state],
    ).then(
        fn=_refresh_keys_for_category,
        inputs=[edit_category],
        outputs=[edit_key],
    ).then(
        fn=lambda k: gr.update(value=k),
        inputs=[saved_key_state],
        outputs=[edit_key],
    ).then(
        fn=_load_entry,
        inputs=[edit_category, edit_key],
        outputs=[tags_box, negative_box, lighting_box, palette_box, composition_box, quality_box, style_box, edit_status],
    )

    save_as_btn.click(
        fn=_save_as,
        inputs=[edit_category, new_key, tags_box, negative_box, lighting_box, palette_box, composition_box, quality_box, style_box],
        outputs=[edit_status, saved_key_state],
    ).then(
        fn=_refresh_keys_for_category,
        inputs=[edit_category],
        outputs=[edit_key],
    ).then(
        fn=lambda k: gr.update(value=k),
        inputs=[saved_key_state],
        outputs=[edit_key],
    ).then(
        fn=_load_entry,
        inputs=[edit_category, edit_key],
        outputs=[tags_box, negative_box, lighting_box, palette_box, composition_box, quality_box, style_box, edit_status],
    )

    delete_btn.click(
        fn=_delete_entry,
        inputs=[edit_category, edit_key, confirm_delete],
        outputs=[edit_status],
    ).then(
        fn=_refresh_keys_for_category,
        inputs=[edit_category],
        outputs=[edit_key],
    ).then(
        fn=_load_entry,
        inputs=[edit_category, edit_key],
        outputs=[tags_box, negative_box, lighting_box, palette_box, composition_box, quality_box, style_box, edit_status],
    )
    
    # Wire pack_search_engine
    pack_search_btn.click(
        fn=_pack_search,
        inputs=[
            pack_search_query,
            pack_search_preset,
            pack_search_format,
            pack_search_max,
            pack_search_match_case,
            pack_search_advanced,
        ],
        outputs=[
            pack_search_results,
            pack_search_results_state,
            pack_search_status,
            pack_result_detail,
        ],
    ).then(
        fn=lambda results: (results[0].get("display_text", "") if results else ""),
        inputs=[pack_search_results_state],
        outputs=[selected_token_box],
    )

    pack_search_results.change(
        fn=_select_pack_result,
        inputs=[pack_search_results, pack_search_results_state],
        outputs=[selected_token_box, pack_result_detail],
    )

    insert_into_preview_btn.click(
        fn=_append_token,
        inputs=[preview_in, selected_token_box],
        outputs=[preview_in],
    )

    if prompt_comp is not None:
        insert_into_prompt_btn.click(
            fn=_append_token,
            inputs=[main_prompt_input, selected_token_box],
            outputs=[main_prompt_input],
        )
    
    
    # Only return generation-affecting controls to the script pipeline.
    return [
        enabled,
        inject_negatives,
        strict,
        include_raw,
        cross_expansion_mode,
        keep_original_if_no_change,
        apply_excludes,
        debug,
        order_from_prompt,
        order_text,
        use_default_order,
        randomize_order,
    ] + category_checks


__all__ = ["build_semantic_ui"]
