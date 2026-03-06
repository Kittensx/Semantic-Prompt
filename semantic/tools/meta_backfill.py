from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

JsonDict = Dict[str, Any]

# --- Data models (UI-friendly) ---

@dataclass
class BackfillFieldSpec:
    """
    Defines one meta field you want to enforce/backfill.
    """
    name: str                               # e.g. "search_tags"
    field_type: str                         # "str" | "list[str]" | "dict" | "bool" | "int"
    default: Any = None                     # used if no generator and no user input
    required: bool = False                  # warn if still missing
    overwrite_existing: bool = False        # if True, replace existing values
    normalize: bool = True                  # trim strings, dedupe lists, etc.

    # Optional: generate a value from file path + existing meta
    generator: Optional[Callable[[Path, JsonDict, JsonDict], Any]] = None

    # Optional: validate; return (ok, message)
    validator: Optional[Callable[[Any], Tuple[bool, str]]] = None


@dataclass
class BackfillIssue:
    path: Path
    category: str
    field: str
    issue_type: str          # "missing" | "wrong_type" | "invalid"
    message: str


@dataclass
class BackfillChange:
    path: Path
    category: str
    field: str
    old_value: Any
    new_value: Any


@dataclass
class BackfillPlan:
    issues: List[BackfillIssue] = field(default_factory=list)
    proposed_changes: List[BackfillChange] = field(default_factory=list)


@dataclass
class BackfillResult:
    applied: List[BackfillChange] = field(default_factory=list)
    skipped: List[BackfillChange] = field(default_factory=list)
    errors: List[Tuple[Path, str]] = field(default_factory=list)


# --- Core tool ---

class MetaBackfillTool:
    """
    UI-first meta backfill engine.
    - No CLI, no printing required.
    - UI can call: build_plan() -> show issues -> apply_plan()
    """

    def __init__(self, packs_root: Path):
        self.packs_root = Path(packs_root).resolve()

    def _read_json(self, p: Path) -> JsonDict:
        return json.loads(p.read_text(encoding="utf-8"))

    def _write_json(self, p: Path, data: JsonDict) -> None:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _backup(self, p: Path) -> Path:
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        bak = p.with_suffix(p.suffix + f".bak_{ts}")
        bak.write_bytes(p.read_bytes())
        return bak

    def _iter_pack_files(self) -> List[Path]:
        return sorted([p for p in self.packs_root.rglob("*.json") if p.is_file()])

    def _get_category(self, data: JsonDict, fallback: str) -> str:
        meta = data.get("_meta")
        if isinstance(meta, dict):
            c = meta.get("category")
            if isinstance(c, str) and c.strip():
                return c.strip()
        return fallback

    def _type_ok(self, value: Any, field_type: str) -> bool:
        if field_type == "str":
            return isinstance(value, str)
        if field_type == "bool":
            return isinstance(value, bool)
        if field_type == "int":
            return isinstance(value, int) and not isinstance(value, bool)
        if field_type == "dict":
            return isinstance(value, dict)
        if field_type == "list[str]":
            return isinstance(value, list) and all(isinstance(x, str) for x in value)
        return True  # unknown: don't block

    def _normalize_value(self, value: Any, field_type: str) -> Any:
        if field_type == "str" and isinstance(value, str):
            return value.strip()
        if field_type == "list[str]" and isinstance(value, list):
            cleaned = []
            seen = set()
            for x in value:
                if not isinstance(x, str):
                    continue
                s = x.strip()
                if not s:
                    continue
                sl = s.lower()
                if sl in seen:
                    continue
                seen.add(sl)
                cleaned.append(s)
            return cleaned
        return value

    def build_plan(
        self,
        specs: List[BackfillFieldSpec],
        *,
        fallback_category_from_filename: bool = True,
    ) -> BackfillPlan:
        """
        Scans pack files and produces:
        - issues (missing/wrong_type/invalid)
        - proposed_changes (what we'd set, but not written yet)
        """
        plan = BackfillPlan()

        for fp in self._iter_pack_files():
            try:
                data = self._read_json(fp)
            except Exception as e:
                plan.issues.append(BackfillIssue(fp, "", "", "invalid", f"JSON read failed: {e!r}"))
                continue

            if not isinstance(data, dict):
                plan.issues.append(BackfillIssue(fp, "", "", "invalid", "Top-level JSON must be an object/dict."))
                continue

            fallback_cat = fp.stem if fallback_category_from_filename else ""
            category = self._get_category(data, fallback_cat)

            meta = data.get("_meta")
            if meta is None or not isinstance(meta, dict):
                meta = {}
                data["_meta"] = meta

            for spec in specs:
                current = meta.get(spec.name, None)

                # Missing
                if spec.name not in meta:
                    plan.issues.append(BackfillIssue(fp, category, spec.name, "missing", "Field is missing."))

                    new_val = None
                    if spec.generator is not None:
                        try:
                            new_val = spec.generator(fp, data, meta)
                        except Exception as e:
                            plan.issues.append(BackfillIssue(fp, category, spec.name, "invalid", f"Generator failed: {e!r}"))
                            continue
                    else:
                        new_val = spec.default

                    if spec.normalize:
                        new_val = self._normalize_value(new_val, spec.field_type)

                    plan.proposed_changes.append(BackfillChange(fp, category, spec.name, None, new_val))
                    continue

                # Present but wrong type
                if current is not None and not self._type_ok(current, spec.field_type):
                    plan.issues.append(BackfillIssue(
                        fp, category, spec.name, "wrong_type",
                        f"Expected {spec.field_type}, got {type(current).__name__}."
                    ))
                    # Only auto-fix wrong type if overwrite_existing
                    if spec.overwrite_existing:
                        new_val = spec.default
                        if spec.generator:
                            try:
                                new_val = spec.generator(fp, data, meta)
                            except Exception:
                                new_val = spec.default
                        if spec.normalize:
                            new_val = self._normalize_value(new_val, spec.field_type)

                        plan.proposed_changes.append(BackfillChange(fp, category, spec.name, current, new_val))
                    continue

                # Validate
                if spec.validator is not None:
                    ok, msg = spec.validator(current)
                    if not ok:
                        plan.issues.append(BackfillIssue(fp, category, spec.name, "invalid", msg))
                        if spec.overwrite_existing:
                            new_val = spec.default
                            if spec.generator:
                                try:
                                    new_val = spec.generator(fp, data, meta)
                                except Exception:
                                    new_val = spec.default
                            if spec.normalize:
                                new_val = self._normalize_value(new_val, spec.field_type)
                            plan.proposed_changes.append(BackfillChange(fp, category, spec.name, current, new_val))

        return plan

    def apply_plan(
        self,
        plan: BackfillPlan,
        *,
        prompt_for_value: Optional[Callable[[BackfillChange], Tuple[bool, Any]]] = None,
        make_backups: bool = True,
    ) -> BackfillResult:
        """
        Applies proposed_changes to files.

        prompt_for_value(change) -> (apply_bool, new_value)
          - UI can show a dialog and let user edit/approve.
          - If None, auto-apply new_value from the plan.
        """
        result = BackfillResult()

        # Group changes by file so we only write each file once
        by_file: Dict[Path, List[BackfillChange]] = {}
        for ch in plan.proposed_changes:
            by_file.setdefault(ch.path, []).append(ch)

        for fp, changes in by_file.items():
            try:
                data = self._read_json(fp)
                if not isinstance(data, dict):
                    result.errors.append((fp, "Top-level JSON not an object/dict"))
                    continue
                meta = data.get("_meta")
                if not isinstance(meta, dict):
                    meta = {}
                    data["_meta"] = meta

                applied_any = False
                for ch in changes:
                    new_val = ch.new_value
                    apply_it = True

                    if prompt_for_value is not None:
                        try:
                            apply_it, new_val = prompt_for_value(ch)
                        except Exception as e:
                            result.errors.append((fp, f"prompt_for_value failed: {e!r}"))
                            apply_it = False

                    if not apply_it:
                        result.skipped.append(ch)
                        continue

                    old_val = meta.get(ch.field, None)
                    meta[ch.field] = new_val
                    result.applied.append(BackfillChange(fp, ch.category, ch.field, old_val, new_val))
                    applied_any = True

                if applied_any:
                    if make_backups:
                        self._backup(fp)
                    self._write_json(fp, data)

            except Exception as e:
                result.errors.append((fp, repr(e)))

        return result