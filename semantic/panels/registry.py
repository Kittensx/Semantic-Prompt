from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, List, Any

@dataclass
class PanelSpec:
    id: str
    title: str
    build_fn: Callable[..., Any]
    order: int = 100
    source: str = "core"      # "core" | "patch" | "user"
    group: str = "general"    # "tools" | "migration" | "debug" ...

_PANELS: List[PanelSpec] = []

def register_panel(id: str, title: str, build_fn: Callable[..., Any], order: int = 100) -> None:
    _PANELS.append(PanelSpec(id=id, title=title, build_fn=build_fn, order=order))

def get_panels() -> List[PanelSpec]:
    return sorted(_PANELS, key=lambda p: (p.order, p.title))

def build_all(container_builder):
    """
    container_builder: a callable that receives (title, build_fn) and creates UI containers.
    This keeps registry independent of Gradio.
    """
    panel_items = []

    for p in get_panels():
        items = container_builder(p.title, p.build_fn) or []
        panel_items.extend(items)

    return panel_items