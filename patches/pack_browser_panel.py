from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import gradio as gr

from semantic.panels.registry import register_panel
from semantic.loaders import PACKS_DIRS
from semantic.patches.bootstrap import category_meta_db

JsonDict = Dict[str, Any]
PAGE_SIZE_DEFAULT = 25


@dataclass
class PackRecord:
    cat_id: str
    category: str
    title: str
    path: Path | None
    meta: JsonDict
    entries: Dict[str, JsonDict]


def _norm_token(s: str) -> str:
    return (s or "").strip().lower().replace("-", "_").replace(" ", "_")


def _first_existing_pack_root() -> Path:
    for p in PACKS_DIRS:
        if p.exists():
            return p
    return PACKS_DIRS[0]


def _iter_json_files() -> Iterable[Path]:
    for root in PACKS_DIRS:
        if root.exists():
            yield from root.rglob("*.json")


def _safe_read_json(path: Path) -> JsonDict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _collect_pack_files() -> Dict[str, Path]:
    by_cat_id: Dict[str, Path] = {}
    for path in _iter_json_files():
        data = _safe_read_json(path)
        meta = data.get("_meta") if isinstance(data.get("_meta"), dict) else {}
        cat_id = str(meta.get("cat_id") or "").strip()
        if cat_id and cat_id not in by_cat_id:
            by_cat_id[cat_id] = path
    return by_cat_id


def _load_pack_records() -> Dict[str, PackRecord]:
    records: Dict[str, PackRecord] = {}
    file_map = _collect_pack_files()

    rows = category_meta_db.conn.execute(
        "SELECT cat_id, category, meta_json FROM category_meta ORDER BY category"
    ).fetchall()

    for row in rows:
        cat_id = str(row[0])
        category = str(row[1] or "")
        meta_json = row[2]
        meta: JsonDict = {}
        if meta_json:
            try:
                meta = json.loads(meta_json)
            except Exception:
                meta = {}
        if not isinstance(meta, dict):
            meta = {}
        meta.setdefault("cat_id", cat_id)
        meta.setdefault("category", category)
        title = str(meta.get("title") or category or cat_id)

        path = file_map.get(cat_id)
        pack_data = _safe_read_json(path) if path else {}

        entries: Dict[str, JsonDict] = {}
        for key, value in pack_data.items():
            if not isinstance(key, str) or key.startswith("_"):
                continue
            if isinstance(value, dict):
                entries[key] = value
            else:
                entries[key] = {"value": value}

        records[category] = PackRecord(
            cat_id=cat_id,
            category=category,
            title=title,
            path=path,
            meta=meta,
            entries=entries,
        )

    return records


def _record_choices(records: Dict[str, PackRecord]) -> List[str]:
    return sorted(records.keys())


def _entry_search_blob(key: str, entry: JsonDict) -> str:
    parts = [key]
    for field in ("tags", "aliases", "search_tags"):
        value = entry.get(field)
        if isinstance(value, list):
            parts.extend(str(x) for x in value)
        elif isinstance(value, str):
            parts.append(value)
    return " ".join(parts).lower()


def _filter_keys(record: PackRecord | None, query: str) -> List[str]:
    if not record:
        return []
    q = (query or "").strip().lower()
    keys = sorted(record.entries.keys())
    if not q:
        return keys
    out: List[str] = []
    for key in keys:
        entry = record.entries.get(key) or {}
        if q in _entry_search_blob(key, entry):
            out.append(key)
    return out


def _paginate(items: List[str], page: int, page_size: int) -> Tuple[List[str], int, int]:
    page_size = max(1, int(page_size or PAGE_SIZE_DEFAULT))
    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    page = max(1, min(int(page or 1), total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], page, total_pages


def _selector_value(mode: str, record: PackRecord | None) -> str:
    if not record:
        return ""
    return record.cat_id if (mode or "").lower().startswith("cat") else record.category


def _directive_text(mode: str, record: PackRecord | None, selected_keys: List[str]) -> str:
    keys = [k for k in selected_keys if k]
    if not record or not keys:
        return ""
    selector = _selector_value(mode, record)
    return f"%%{{{selector}={'|'.join(keys)}}}%%"


def _raw_key_text(selected_keys: List[str]) -> str:
    keys = [k for k in selected_keys if k]
    return "|".join(keys)


def _pack_summary(record: PackRecord | None) -> str:
    if not record:
        return "Select a pack/category."
    lines = [
        f"category: {record.category}",
        f"cat_id: {record.cat_id}",
        f"title: {record.title}",
        f"file: {record.path.as_posix() if record.path else '(not found on disk)'}",
        f"entry_count: {len(record.entries)}",
    ]
    for field in [
        "description",
        "notes",
        "generator_family",
        "generator_slot",
        "generatable",
        "search_tags",
        "related_categories",
        "aliases",
    ]:
        if field in record.meta:
            lines.append(f"{field}: {record.meta.get(field)}")
    return "\n".join(lines)


def _entry_details(record: PackRecord | None, selected_keys: List[str]) -> JsonDict:
    if not record or not selected_keys:
        return {}
    key = selected_keys[-1]
    entry = record.entries.get(key) or {}
    details: JsonDict = {"key": key}
    if isinstance(entry, dict):
        for k, v in entry.items():
            details[k] = v
    else:
        details["value"] = entry
    return details


def build_pack_browser_panel():
    records = _load_pack_records()
    categories = _record_choices(records)

    records_state = gr.State(records)
    filtered_keys_state = gr.State([])
    selected_keys_state = gr.State([])
    current_page_state = gr.State(1)

    with gr.Column():
        gr.Markdown("### Pack Browser")
        gr.Markdown(
            "Browse packs by category, inspect entry fields, and build directive text in the form "
            "`%%{category_or_cat_id=key1|key2}%%`."
        )

        with gr.Row():
            pack_picker = gr.Dropdown(
                label="Category / Pack",
                choices=categories,
                value=categories[0] if categories else None,
                interactive=True,
            )
            ref_mode = gr.Radio(
                label="Directive selector",
                choices=["category", "cat_id"],
                value="category",
                interactive=True,
            )

        with gr.Row():
            search_box = gr.Textbox(label="Search keys / tags / aliases", placeholder="east asian, bangs, zipper...")
            page_size = gr.Number(label="Page size", value=PAGE_SIZE_DEFAULT, precision=0)

        with gr.Row():
            prev_btn = gr.Button("Previous")
            next_btn = gr.Button("Next")
            page_num = gr.Number(label="Page", value=1, precision=0)
            go_btn = gr.Button("Go")
            page_status = gr.Markdown("Page 1 of 1")

        entry_checks = gr.CheckboxGroup(label="Entries on current page", choices=[], value=[], show_label=True)

        with gr.Row():
            select_page_btn = gr.Button("Select page")
            clear_page_btn = gr.Button("Clear page")
            clear_all_btn = gr.Button("Clear all")

        selected_count = gr.Markdown("Selected: 0")

        with gr.Row():
            pack_summary = gr.Textbox(label="Pack summary", lines=10)
            entry_json = gr.JSON(label="Selected entry details")

        with gr.Row():
            raw_preview = gr.Textbox(label="Raw key text", lines=2)
            directive_preview = gr.Textbox(label="Directive preview", lines=2)

        with gr.Row():
            build_raw_btn = gr.Button("Build key text")
            build_directive_btn = gr.Button("Build directive")

    def _record_from_category(records_obj: Dict[str, PackRecord], category: str) -> PackRecord | None:
        return records_obj.get(category or "")

    def _render_page(
        category: str,
        query: str,
        page: int,
        page_size_val: float,
        selected_keys: List[str],
        records_obj: Dict[str, PackRecord],
        mode: str,
    ):
        record = _record_from_category(records_obj, category)
        filtered = _filter_keys(record, query)
        page_items, page, total_pages = _paginate(filtered, int(page or 1), int(page_size_val or PAGE_SIZE_DEFAULT))
        selected_set = set(selected_keys or [])
        page_selected = [k for k in page_items if k in selected_set]
        return (
            filtered,
            selected_keys or [],
            page,
            gr.update(choices=page_items, value=page_selected),
            gr.update(value=page),
            f"Page {page} of {total_pages}  |  Filtered entries: {len(filtered)}",
            f"Selected: {len(selected_set)}",
            _pack_summary(record),
            _entry_details(record, page_selected or (selected_keys or [])),
            _raw_key_text(selected_keys or []),
            _directive_text(mode, record, selected_keys or []),
        )

    def _set_category(category: str, query: str, page_size_val: float, records_obj: Dict[str, PackRecord], mode: str):
        return _render_page(category, query, 1, page_size_val, [], records_obj, mode)

    def _merge_page_selection(
        current_page_values: List[str],
        category: str,
        query: str,
        page: int,
        page_size_val: float,
        selected_keys: List[str],
        filtered_keys: List[str],
        records_obj: Dict[str, PackRecord],
        mode: str,
    ):
        record = _record_from_category(records_obj, category)
        filtered = filtered_keys or _filter_keys(record, query)
        page_items, page, total_pages = _paginate(filtered, int(page or 1), int(page_size_val or PAGE_SIZE_DEFAULT))

        selected_set = set(selected_keys or [])
        for item in page_items:
            if item in selected_set and item not in (current_page_values or []):
                selected_set.remove(item)
        for item in (current_page_values or []):
            selected_set.add(item)

        merged = sorted(selected_set)
        page_selected = [k for k in page_items if k in selected_set]
        return (
            merged,
            gr.update(choices=page_items, value=page_selected),
            f"Selected: {len(merged)}",
            _entry_details(record, page_selected or merged),
            _raw_key_text(merged),
            _directive_text(mode, record, merged),
        )

    def _go_to_page(category: str, query: str, page: float, page_size_val: float, selected_keys: List[str], records_obj: Dict[str, PackRecord], mode: str):
        return _render_page(category, query, int(page or 1), page_size_val, selected_keys, records_obj, mode)

    def _change_page(delta: int, category: str, query: str, page: float, page_size_val: float, selected_keys: List[str], records_obj: Dict[str, PackRecord], mode: str):
        new_page = int(page or 1) + int(delta)
        return _render_page(category, query, new_page, page_size_val, selected_keys, records_obj, mode)

    def _select_page(entry_values: List[str], category: str, query: str, page: float, page_size_val: float, selected_keys: List[str], filtered_keys: List[str], records_obj: Dict[str, PackRecord], mode: str):
        record = _record_from_category(records_obj, category)
        filtered = filtered_keys or _filter_keys(record, query)
        page_items, page, total_pages = _paginate(filtered, int(page or 1), int(page_size_val or PAGE_SIZE_DEFAULT))
        selected_set = set(selected_keys or [])
        selected_set.update(page_items)
        merged = sorted(selected_set)
        return (
            merged,
            gr.update(choices=page_items, value=page_items),
            f"Selected: {len(merged)}",
            _entry_details(record, page_items or merged),
            _raw_key_text(merged),
            _directive_text(mode, record, merged),
        )

    def _clear_page(entry_values: List[str], category: str, query: str, page: float, page_size_val: float, selected_keys: List[str], filtered_keys: List[str], records_obj: Dict[str, PackRecord], mode: str):
        record = _record_from_category(records_obj, category)
        filtered = filtered_keys or _filter_keys(record, query)
        page_items, page, total_pages = _paginate(filtered, int(page or 1), int(page_size_val or PAGE_SIZE_DEFAULT))
        selected_set = set(selected_keys or [])
        for item in page_items:
            selected_set.discard(item)
        merged = sorted(selected_set)
        return (
            merged,
            gr.update(choices=page_items, value=[]),
            f"Selected: {len(merged)}",
            _entry_details(record, merged),
            _raw_key_text(merged),
            _directive_text(mode, record, merged),
        )

    def _clear_all(category: str, query: str, page: float, page_size_val: float, records_obj: Dict[str, PackRecord], mode: str):
        record = _record_from_category(records_obj, category)
        filtered = _filter_keys(record, query)
        page_items, page, total_pages = _paginate(filtered, int(page or 1), int(page_size_val or PAGE_SIZE_DEFAULT))
        return (
            [],
            gr.update(choices=page_items, value=[]),
            "Selected: 0",
            {},
            "",
            "",
        )

    def _rebuild_directive(mode: str, category: str, selected_keys: List[str], records_obj: Dict[str, PackRecord]):
        record = _record_from_category(records_obj, category)
        return _directive_text(mode, record, selected_keys or [])

    def _rebuild_raw(selected_keys: List[str]):
        return _raw_key_text(selected_keys or [])

    init_outputs = [
        filtered_keys_state,
        selected_keys_state,
        current_page_state,
        entry_checks,
        page_num,
        page_status,
        selected_count,
        pack_summary,
        entry_json,
        raw_preview,
        directive_preview,
    ]

    pack_picker.change(
        fn=_set_category,
        inputs=[pack_picker, search_box, page_size, records_state, ref_mode],
        outputs=init_outputs,
    )

    search_box.submit(
        fn=_set_category,
        inputs=[pack_picker, search_box, page_size, records_state, ref_mode],
        outputs=init_outputs,
    )

    go_btn.click(
        fn=_go_to_page,
        inputs=[pack_picker, search_box, page_num, page_size, selected_keys_state, records_state, ref_mode],
        outputs=init_outputs,
    )

    prev_btn.click(
        fn=lambda category, query, page, page_size_val, selected_keys, records_obj, mode: _change_page(-1, category, query, page, page_size_val, selected_keys, records_obj, mode),
        inputs=[pack_picker, search_box, current_page_state, page_size, selected_keys_state, records_state, ref_mode],
        outputs=init_outputs,
    )

    next_btn.click(
        fn=lambda category, query, page, page_size_val, selected_keys, records_obj, mode: _change_page(1, category, query, page, page_size_val, selected_keys, records_obj, mode),
        inputs=[pack_picker, search_box, current_page_state, page_size, selected_keys_state, records_state, ref_mode],
        outputs=init_outputs,
    )

    entry_checks.change(
        fn=_merge_page_selection,
        inputs=[entry_checks, pack_picker, search_box, current_page_state, page_size, selected_keys_state, filtered_keys_state, records_state, ref_mode],
        outputs=[selected_keys_state, entry_checks, selected_count, entry_json, raw_preview, directive_preview],
    )

    select_page_btn.click(
        fn=_select_page,
        inputs=[entry_checks, pack_picker, search_box, current_page_state, page_size, selected_keys_state, filtered_keys_state, records_state, ref_mode],
        outputs=[selected_keys_state, entry_checks, selected_count, entry_json, raw_preview, directive_preview],
    )

    clear_page_btn.click(
        fn=_clear_page,
        inputs=[entry_checks, pack_picker, search_box, current_page_state, page_size, selected_keys_state, filtered_keys_state, records_state, ref_mode],
        outputs=[selected_keys_state, entry_checks, selected_count, entry_json, raw_preview, directive_preview],
    )

    clear_all_btn.click(
        fn=_clear_all,
        inputs=[pack_picker, search_box, current_page_state, page_size, records_state, ref_mode],
        outputs=[selected_keys_state, entry_checks, selected_count, entry_json, raw_preview, directive_preview],
    )

    build_raw_btn.click(fn=_rebuild_raw, inputs=[selected_keys_state], outputs=[raw_preview])
    build_directive_btn.click(
        fn=_rebuild_directive,
        inputs=[ref_mode, pack_picker, selected_keys_state, records_state],
        outputs=[directive_preview],
    )

    ref_mode.change(
        fn=_rebuild_directive,
        inputs=[ref_mode, pack_picker, selected_keys_state, records_state],
        outputs=[directive_preview],
    )

    if categories:
        initial = _set_category(categories[0], "", PAGE_SIZE_DEFAULT, records, "category")
        # Return initial updates in a load-compatible way is unnecessary here; panel initializes on first interaction.

    return [
        pack_picker,
        ref_mode,
        search_box,
        page_size,
        prev_btn,
        next_btn,
        page_num,
        go_btn,
        entry_checks,
        select_page_btn,
        clear_page_btn,
        clear_all_btn,
        selected_count,
        pack_summary,
        entry_json,
        raw_preview,
        directive_preview,
    ]


register_panel(
    id="pack_browser",
    title="Pack Browser",
    build_fn=build_pack_browser_panel,
    order=60,
)
