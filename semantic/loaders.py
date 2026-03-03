import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

PACKS_DIR = BASE_DIR / "packs"
TRIGGERS_DIR = BASE_DIR / "triggers"


class SemanticRegistry:

    def __init__(self):

        self.packs = {}
        self.triggers = {}
        self.dynamic = {}  
        self.load_packs()
        self.load_triggers()
        self.load_dynamic()  

     # --- NEW ---
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

    def load_packs(self):

        if not PACKS_DIR.exists():
            return

        for file in PACKS_DIR.rglob("*.json"):

            data = self._load_json(file)

            category = data.get("_meta", {}).get("category")

            if not category:
                continue

            self.packs.setdefault(category, {})

            for key, value in data.items():

                if key.startswith("_"):
                    continue                

                canon_key = key.lower()
                self.packs[category][canon_key] = value

                # NEW: aliases
                aliases = value.get("aliases")
                if isinstance(aliases, list):
                    for a in aliases:
                        if not isinstance(a, str):
                            continue
                        a_key = a.strip().lower()
                        if not a_key:
                            continue
                        # Don't override real keys
                        if a_key in self.packs[category]:
                            continue
                        self.packs[category][a_key] = value

                self.packs[category][key.lower()] = value


    def load_triggers(self):

        file = TRIGGERS_DIR / "triggers.json"

        if not file.exists():
            return

        data = self._load_json(file)

        for key, value in data.items():

            if key.startswith("_"):
                continue

            self.triggers[key.lower()] = value


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
        text_lc = (text or "").lower()

        matches = {}

        # Sort triggers by phrase length (desc) so longer phrases are checked first
        phrases = sorted(self.triggers.keys(), key=len, reverse=True)

        for phrase in phrases:
            if not phrase:
                continue

            if " " in phrase:
                # Multi-word phrase: substring match
                if phrase in text_lc:
                    matches[phrase] = self.triggers[phrase]
            else:
                # Single word: word-boundary match to avoid "rain" matching "brain"
                # Escape phrase for regex safety
                import re
                pat = r"\b" + re.escape(phrase) + r"\b"
                if re.search(pat, text_lc):
                    matches[phrase] = self.triggers[phrase]

        return matches
        
    def reload_all(self):
        self.packs = {}
        self.triggers = {}
        self.dynamic = {}  
        self.load_packs()
        self.load_triggers()
        self.load_dynamic()  


registry = SemanticRegistry()