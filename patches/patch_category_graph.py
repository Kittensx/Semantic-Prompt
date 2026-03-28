from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

@dataclass
class CategoryNode:
    id: str
    title: str = ""
    parents: Set[str] = field(default_factory=set)
    children: Set[str] = field(default_factory=set)
    related: Set[str] = field(default_factory=set)
    aliases: Set[str] = field(default_factory=set)

class CategoryGraph:
    def __init__(self) -> None:
        self.nodes: Dict[str, CategoryNode] = {}
        self.unindexed: Set[str] = set()

    def node(self, cat: str) -> CategoryNode:
        n = self.nodes.get(cat)
        if not n:
            n = CategoryNode(id=cat, title=cat)
            self.nodes[cat] = n
        return n

    def add_edge_parent_child(self, parent: str, child: str) -> None:
        p = self.node(parent)
        c = self.node(child)
        p.children.add(child)
        c.parents.add(parent)

    def infer_dot_parent(self, cat: str) -> Optional[str]:
        if "." not in cat:
            return None
        return cat.rsplit(".", 1)[0] or None

def apply(settings: Dict[str, Any], manifest: Dict[str, Any]) -> None:
    import semantic_prompt.registry as registry_mod

    index_path = settings.get("category_index")
    enable = bool(settings.get("enable_category_graph", True))

    if not enable:
        return

    # Attach graph to registry instances after load_packs
    original_load_packs = registry_mod.SemanticRegistry.load_packs

    def load_packs_with_graph(self) -> None:
        # run the (possibly patched) loader
        original_load_packs(self)

        graph = CategoryGraph()

        # 1) Load master index if present
        index_data: Dict[str, Any] = {}
        if index_path:
            p = Path(index_path)
            if p.exists():
                index_data = json.loads(p.read_text(encoding="utf-8"))

        # index_data format:
        # { "cat.id": { "title": "...", "parents": [...], "children": [...], "related_categories": [...], "aliases": [...] }, ... }
        for cat, meta in index_data.items():
            if cat == "_meta":
                continue
            n = graph.node(cat)
            if isinstance(meta, dict):
                if meta.get("title"):
                    n.title = meta["title"]
                for a in (meta.get("aliases") or []):
                    n.aliases.add(str(a))
                for r in (meta.get("related_categories") or []):
                    n.related.add(str(r))
                # parents/children edges
                for parent in (meta.get("parents") or []):
                    graph.add_edge_parent_child(str(parent), cat)
                for child in (meta.get("children") or []):
                    graph.add_edge_parent_child(cat, str(child))

        indexed_set = {k for k in index_data.keys() if k != "_meta"}

        # 2) Merge pack-local meta
        # Your registry structure is packs[category] = dict(keys...)
        for cat in getattr(self, "packs", {}).keys():
            n = graph.node(cat)
            # if not in index, mark unindexed (UI can show "Legacy/Unindexed")
            if indexed_set and cat not in indexed_set:
                graph.unindexed.add(cat)

            # read pack meta if you store it; if not, we can’t pull title/parents without extending loader.
            # But we can still infer dot parent if missing.
            inferred_parent = graph.infer_dot_parent(cat)
            if inferred_parent and not n.parents:
                graph.add_edge_parent_child(inferred_parent, cat)

        # 3) Attach helpers to registry instance
        self.category_graph = graph  # type: ignore[attr-defined]

    registry_mod.SemanticRegistry.load_packs = load_packs_with_graph  # type: ignore[assignment]