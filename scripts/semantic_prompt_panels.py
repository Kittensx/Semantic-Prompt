import gradio as gr

from semantic.panels.registry import register_panel
from semantic.tools.search_tag_suggester import SearchTagSuggester, build_search_tags_backfill_plan

def build_search_tag_panel():
    with gr.Row():
        query = gr.Textbox(label="Scan packs for suggested search tags", placeholder="(no query needed) just scan")
    scan_btn = gr.Button("Scan")
    out = gr.JSON(label="Suggestions (preview)")

    def do_scan(_):
        # resolve your packs folder; loaders.py already has PACKS_DIRS but keep it local here
        from semantic.loaders import PACKS_DIRS  # uses your BASE_DIR pattern :contentReference[oaicite:0]{index=0}
        suggester = SearchTagSuggester(PACKS_DIRS)
        suggestions = suggester.suggest_for_folder()
        # return preview only; apply happens in another action
        return [ {"file": str(s.path), "category": s.category, "search_tags": s.suggested_search_tags[:20]} for s in suggestions[:50] ]

    scan_btn.click(do_scan, inputs=[query], outputs=[out])

register_panel(
    id="search_tags",
    title="Search Tag Builder",
    build_fn=build_search_tag_panel,
    order=50,
)