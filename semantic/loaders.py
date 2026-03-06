import json
import os
from pathlib import Path
import re
from dataclasses import dataclass
from typing import List, Dict, Any

BASE_DIR = Path(__file__).resolve().parent  # .../semantic

PACKS_DIRS = [
    BASE_DIR / "packs",
    BASE_DIR / "user" / "packs"
]

PANELS_DIRS = [
    BASE_DIR / "panels",           
    BASE_DIR / "user" / "panels",
    BASE_DIR / "addons" / "panels",
]

TOOLS_DIRS = [
    BASE_DIR / "tools",         
    BASE_DIR / "user" / "tools",
    BASE_DIR / "addons" / "tools",
]

ADDONS_DIR = BASE_DIR / "addons"

TRIGGERS_DIRS = [
    BASE_DIR / "triggers",
    BASE_DIR / "user" / "triggers",
    BASE_DIR / "addons" / "triggers"
    ]


_RE_CAMEL = re.compile(r"([a-z])([A-Z])")
_RE_PUNCT = re.compile(r"[^\w\s]")
_RE_WS = re.compile(r"\s+")



@dataclass
class TriggerRec:
    raw: str
    norm: str
    tokens: List[str]
    priority: int
    min_tokens: int
    payload: Dict[str, Any]
    
def normalize_phrase(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = _RE_CAMEL.sub(r"\1 \2", s)
    s = s.lower()
    s = s.replace("_", " ").replace("-", " ")
    s = _RE_PUNCT.sub(" ", s)
    s = _RE_WS.sub(" ", s)
    return s.strip()

class SemanticRegistry:

    def __init__(self):

        self.packs = {}
        self.triggers = {}
        self.dynamic = {}  
        self.load_packs()
        self.load_triggers()
        self.load_dynamic()  

    def build_trigger_index(self):

        index = []

        for raw, payload in self.triggers.items():

            priority = 50
            min_tokens = 1

            if isinstance(payload, dict):
                priority = payload.get("priority", 50)
                min_tokens = payload.get("min_tokens", 1)

            norm = normalize_phrase(raw)
            tokens = norm.split()

            if min_tokens == 1 and len(tokens) >= 2:
                min_tokens = 2

            index.append(
                TriggerRec(
                    raw=raw,
                    norm=norm,
                    tokens=tokens,
                    priority=priority,
                    min_tokens=min_tokens,
                    payload=payload
                )
            )

        index.sort(key=lambda t: (t.priority, len(t.tokens)), reverse=True)

        self._trigger_index = index
    def load_dynamic(self):
        #  LoRA discovery disabled for this release (UI/editor WIP)
        #self.dynamic["lora"] = {k.lower(): {"_dynamic": True} for k in self._list_loras()}
        pass

    # --- NEW ---
    def _list_loras(self) -> list[str]:
        """
        Best-effort LoRA discovery.
        Uses A1111's standard models/Lora folder relative to webui root.
        (This runs inside A1111, so __file__ isn't the webui root.)
        """
        # Try common A1111 layout: <webui_root>/models/Lora
        # If this doesn't match your setup, you can extend with shared.opts/custom paths later.
        candidates = []
        try:
            import modules.paths as paths  # A1111 provides this
            webui_root = Path(paths.script_path)
            candidates.append(webui_root / "models" / "Lora")
        except Exception:
            pass

        names = []
        exts = {".safetensors", ".pt", ".ckpt"}
        for base in candidates:
            if not base or not base.exists():
                continue
            for p in base.rglob("*"):
                if p.is_file() and p.suffix.lower() in exts:
                    names.append(p.stem)  # key users recognize in <lora:NAME:W>
        # de-dupe preserve order
        seen = set()
        out = []
        for n in names:
            nl = n.lower()
            if nl in seen:
                continue
            seen.add(nl)
            out.append(n)
        return out

    def iter_pack_files(self):
        """
        Yields all pack .json files from:
          - semantic/packs/**
          - semantic/user/packs/**
          - semantic/addons/<addon_name>/packs/**
        """
        # core + user pack roots
        for d in PACKS_DIRS:
            if not d.exists():
                continue
            yield from d.rglob("*.json")

        # addon bundle roots
        if ADDONS_DIR.exists():
            for addon in sorted(ADDONS_DIR.iterdir()):
                if not addon.is_dir():
                    continue
                pdir = addon / "packs"
                if pdir.exists():
                    yield from pdir.rglob("*.json")


    def load_packs(self):
        for file in self.iter_pack_files():
            data = self._load_json(file)

            category = data.get("_meta", {}).get("category")
            if not category:
                continue

            category = str(category).strip().lower()
            self.packs.setdefault(category, {})

            for key, value in data.items():
                if not isinstance(key, str) or key.startswith("_"):
                    continue

                canon_key = key.strip().lower()
                self.packs[category][canon_key] = value

                # aliases (guard value type)
                if isinstance(value, dict):
                    aliases = value.get("aliases")
                    if isinstance(aliases, list):
                        for a in aliases:
                            if not isinstance(a, str):
                                continue
                            a_key = a.strip().lower()
                            if not a_key:
                                continue
                            if a_key in self.packs[category]:
                                continue
                            self.packs[category][a_key] = value


    def iter_trigger_files(self):
        # core triggers
        core = BASE_DIR / "triggers" / "triggers.json"
        if core.exists():
            yield core

        # addon triggers: addons/<addon>/triggers/triggers.json
        addons_root = BASE_DIR / "addons"
        if addons_root.exists():
            for addon in sorted(addons_root.iterdir()):
                if not addon.is_dir():
                    continue
                tf = addon / "triggers" / "triggers.json"
                if tf.exists():
                    yield tf

        # user triggers override last
        user = BASE_DIR / "user" / "triggers" / "triggers.json"
        if user.exists():
            yield user


    def load_triggers(self):
        # core triggers only by default; add user/addons if present
        trigger_files = [
            BASE_DIR / "triggers" / "triggers.json",
            BASE_DIR / "user" / "triggers" / "triggers.json",
        ]

        # optional: addon bundles: semantic/addons/<addon>/triggers/triggers.json
        if ADDONS_DIR.exists():
            for addon in sorted(ADDONS_DIR.iterdir()):
                if not addon.is_dir():
                    continue
                tf = addon / "triggers" / "triggers.json"
                trigger_files.append(tf)

        for file in trigger_files:
            if not file.exists():
                continue

            # skip empty files safely (prevents JSONDecodeError)
            try:
                txt = file.read_text(encoding="utf-8").strip()
            except Exception:
                continue
            if not txt:
                continue

            try:
                data = json.loads(txt)
            except Exception:
                print(f"[Semantic Prompt] WARNING: invalid triggers JSON skipped: {file}")
                continue

            if not isinstance(data, dict):
                continue

            for key, value in data.items():
                if not isinstance(key, str) or key.startswith("_"):
                    continue
                self.triggers[key.strip().lower()] = value


    def _load_json(self, path):

        with open(path, "r", encoding="utf-8") as f:

            return json.load(f)


    def get_categories(self):
        # include dynamic categories too
        cats = set(self.packs.keys())
        cats.update(self.dynamic.keys())
        return sorted(cats)


    def get_pack(self, category, key):
        # allow lookups into dynamic categories (even if no JSON entry exists)
        cat = (category or "").lower()
        k = (key or "").lower()
        return self.packs.get(cat, {}).get(k) or self.dynamic.get(cat, {}).get(k)


    def find_triggers(self, text):

        prompt_norm = normalize_phrase(text or "")
        prompt_tokens = prompt_norm.split()

        matches = {}

        if not hasattr(self, "_trigger_index"):
            self.build_trigger_index()

        scored = []

        for tr in self._trigger_index:

            if tr.norm in prompt_norm:
                score = 3.0
            else:
                hit = sum(1 for t in tr.tokens if t in prompt_tokens)

                if hit < tr.min_tokens:
                    continue

                coverage = hit / len(tr.tokens)
                score = 1.0 * coverage

            score *= (tr.priority / 100)

            if score > 0:
                scored.append((score, tr))

        scored.sort(key=lambda x: x[0], reverse=True)

        for score, tr in scored[:10]:
            matches[tr.raw] = tr.payload

        return matches
        
    def reload_all(self):
        self.packs = {}
        self.triggers = {}
        self.dynamic = {}  
        self.load_packs()
        self.load_triggers()
        self.load_dynamic()  
        self.build_trigger_index()


registry = SemanticRegistry()