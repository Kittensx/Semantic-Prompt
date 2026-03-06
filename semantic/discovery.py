from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class DiscoveryReport:
    packs_found: List[Path] = field(default_factory=list)
    panel_modules_loaded: List[str] = field(default_factory=list)
    tool_modules_loaded: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def _iter_addon_roots(addons_dir: Path) -> List[Path]:
    roots = []
    if not addons_dir.exists():
        return roots
    for d in sorted(addons_dir.iterdir()):
        if d.is_dir():
            roots.append(d)
    return roots


def _scan_json_packs(pack_dirs: List[Path]) -> List[Path]:
    out: List[Path] = []
    for d in pack_dirs:
        if not d.exists():
            continue
        out.extend([p for p in d.rglob("*.json") if p.is_file()])
    return sorted(set(out))


def _load_py_module_from_file(module_name: str, file_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for {file_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)


def _import_py_folder(folder: Path, namespace: str, report_list: List[str], errors: List[str]) -> None:
    """
    Imports every .py file in a folder (non-recursive by default).
    Import side effects can call register_panel/register_tool.
    """
    if not folder.exists():
        return
    for fp in sorted(folder.glob("*.py")):
        if not fp.is_file():
            continue
        if fp.name.startswith("_"):
            continue
        module_name = f"{namespace}.{fp.stem}"
        try:
            _load_py_module_from_file(module_name, fp)
            report_list.append(module_name)
        except Exception as e:
            errors.append(f"Failed to import {fp}: {e!r}")


def discover_everything(
    *,
    base_dir: Path,
    packs_dirs: List[Path],
    panels_dirs: List[Path],
    tools_dirs: List[Path],
    addons_dir: Optional[Path] = None,
) -> DiscoveryReport:
    """
    - Finds JSON pack files
    - Imports user/addon panel modules (to register UI panels)
    - Imports user/addon tool modules (to register tools)
    """
    report = DiscoveryReport()

    # Addons expand
    expanded_pack_dirs = list(packs_dirs)
    expanded_panel_dirs = list(panels_dirs)
    expanded_tool_dirs = list(tools_dirs)

    if addons_dir:
        for addon_root in _iter_addon_roots(addons_dir):
            expanded_pack_dirs.append(addon_root / "packs")
            expanded_panel_dirs.append(addon_root / "panels")
            expanded_tool_dirs.append(addon_root / "tools")

    # 1) Packs
    report.packs_found = _scan_json_packs(expanded_pack_dirs)

    # 2) Panels (import .py files that call register_panel)
    for i, d in enumerate(expanded_panel_dirs):
        _import_py_folder(d, namespace=f"semantic._ext_panels_{i}", report_list=report.panel_modules_loaded, errors=report.errors)

    # 3) Tools (import .py files that call register_tool)
    for i, d in enumerate(expanded_tool_dirs):
        _import_py_folder(d, namespace=f"semantic._ext_tools_{i}", report_list=report.tool_modules_loaded, errors=report.errors)

    return report