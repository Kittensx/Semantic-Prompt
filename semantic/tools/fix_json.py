#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class JsonProblem:
    path: Path
    message: str
    line: Optional[int] = None
    col: Optional[int] = None
    pos: Optional[int] = None
    extra: Optional[str] = None  # context / hints


def read_text_best_effort(p: Path) -> tuple[str, str]:
    """
    Returns (text, encoding_used). Tries utf-8-sig to auto-strip BOM.
    Falls back to utf-8 with replacement if needed.
    """
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8 (replacement)"


def context_snippet(text: str, line: int, col: int, radius: int = 2) -> str:
    lines = text.splitlines()
    idx = max(0, line - 1)
    start = max(0, idx - radius)
    end = min(len(lines), idx + radius + 1)

    out = []
    width = len(str(end))
    for i in range(start, end):
        prefix = f"{i+1:>{width}} | "
        out.append(prefix + lines[i])
        if i == idx:
            caret_pad = " " * (len(prefix) + max(col - 1, 0))
            out.append(caret_pad + "^")
    return "\n".join(out)


def check_one(path: Path) -> list[JsonProblem]:
    problems: list[JsonProblem] = []
    text, enc = read_text_best_effort(path)

    # Quick hint if BOM existed (utf-8-sig would strip it, but good to know)
    if path.read_bytes().startswith(b"\xef\xbb\xbf"):
        problems.append(
            JsonProblem(
                path=path,
                message="File contains UTF-8 BOM (Byte Order Mark).",
                extra="Most parsers tolerate it, but some tools don’t. Re-save as UTF-8 (no BOM).",
            )
        )

    try:
        # json.loads gives best line/col reporting
        json.loads(text)
    except json.JSONDecodeError as e:
        hint = None

        # Common causes for: Expecting property name enclosed in double quotes
        # - trailing comma before } or ]
        # - single quotes around keys/strings
        # - comments // or /* */
        # - a stray "}" or "]" or junk character
        nearby = context_snippet(text, e.lineno, e.colno)
        hint_lines = []
        hint_lines.append("Common fixes for this error:")
        hint_lines.append("- Remove trailing commas before } or ]")
        hint_lines.append("- Ensure keys and strings use double quotes (\"...\") not single quotes ('...')")
        hint_lines.append("- Remove comments (// ... or /* ... */) — JSON doesn’t allow them")
        hint_lines.append("- Make sure the file is exactly one JSON value (no extra text after the closing brace)")
        hint = "\n".join(hint_lines)

        problems.append(
            JsonProblem(
                path=path,
                message=e.msg,
                line=e.lineno,
                col=e.colno,
                pos=e.pos,
                extra=f"Encoding used: {enc}\n\n{nearby}\n\n{hint}",
            )
        )
        return problems

    # Extra strict check: ensure there is no trailing non-whitespace after the JSON value
    # (Sometimes tools append stray characters that some loaders choke on.)
    try:
        decoder = json.JSONDecoder()
        obj, end = decoder.raw_decode(text.lstrip())
        trailing = text.lstrip()[end:].strip()
        if trailing:
            problems.append(
                JsonProblem(
                    path=path,
                    message="Trailing non-whitespace characters after valid JSON.",
                    extra=f"First trailing chars: {trailing[:80]!r}\nRemove anything after the final closing brace/bracket.",
                )
            )
    except Exception:
        # already valid by json.loads; ignore
        pass

    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Scan a folder for broken JSON and report file + line/col + context.")
    ap.add_argument("folder", type=str, help="Folder containing JSON files")
    ap.add_argument("--recursive", action="store_true", help="Recurse into subfolders")
    ap.add_argument("--ext", default=".json", help="File extension to scan (default: .json)")
    args = ap.parse_args()

    root = Path(args.folder).expanduser().resolve()
    if not root.exists():
        print(f"Folder not found: {root}")
        return 2

    glob_pat = f"**/*{args.ext}" if args.recursive else f"*{args.ext}"
    files = sorted(root.glob(glob_pat))

    if not files:
        print(f"No files matched {glob_pat} in {root}")
        return 0

    all_problems: list[JsonProblem] = []
    for f in files:
        if f.is_file():
            all_problems.extend(check_one(f))

    if not all_problems:
        print(f"OK: {len(files)} files scanned, no issues found.")
        return 0

    # Print grouped by file
    by_file: dict[Path, list[JsonProblem]] = {}
    for p in all_problems:
        by_file.setdefault(p.path, []).append(p)

    print(f"Found issues in {len(by_file)} file(s) out of {len(files)} scanned.\n")
    for path, probs in by_file.items():
        print("=" * 90)
        print(path)
        for prob in probs:
            loc = ""
            if prob.line is not None and prob.col is not None:
                loc = f" (line {prob.line}, col {prob.col})"
            print(f"- {prob.message}{loc}")
            if prob.extra:
                print(prob.extra)
                print()
    print("=" * 90)

    # Return non-zero so it can be used in CI/scripts
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
    