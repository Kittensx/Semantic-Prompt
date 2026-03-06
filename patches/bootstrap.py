from __future__ import annotations
import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple


def _load_callable(path: str) -> Callable:
    # "module.sub:func"
    if ":" not in path:
        raise ValueError(f"Invalid callable path (expected module:func): {path}")
    mod_name, fn_name = path.split(":", 1)
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, fn_name, None)
    if not callable(fn):
        raise TypeError(f"Callable not found: {path}")
    return fn


def run_from_manifest(manifest_path: str | Path) -> Any:
    manifest_path = Path(manifest_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    settings: Dict[str, Any] = data.get("settings", {}) or {}
    patch_list: List[str] = data.get("patches", []) or []
    entrypoint: str = data.get("entrypoint")

    if not entrypoint:
        raise ValueError("Manifest missing 'entrypoint'")

    # Apply patches
    for p in patch_list:
        fn = _load_callable(p)
        fn(settings=settings, manifest=data)

    # Run entrypoint
    entry_fn = _load_callable(entrypoint)
    return entry_fn()


if __name__ == "__main__":
    # Default manifest location
    run_from_manifest(Path(__file__).resolve().parents[1] / "config" / "program.json")