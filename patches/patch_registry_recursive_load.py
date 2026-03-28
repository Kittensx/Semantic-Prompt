from __future__ import annotations
from pathlib import Path
from typing import Any, Dict

def apply(settings: Dict[str, Any], manifest: Dict[str, Any]) -> None:
    # Import your existing registry module
    import semantic_prompt.registry as registry_mod

    packs_dirs = Path(settings.get("packs_dirs", "packs")).resolve()

    original_load_packs = registry_mod.SemanticRegistry.load_packs

    def load_packs_recursive(self) -> None:
        # If your registry already has PACKS_DIRS, prefer the manifest override
        # but keep fallback to existing behavior if missing.
        self.packs.clear()

        if not packs_dirs.exists():
            # fallback to original if directory isn't found
            return original_load_packs(self)

        # IMPORTANT: recursive scan
        for file in packs_dirs.rglob("*.json"):
            # replicate your original parse logic (call internal helpers if they exist)
            # If original loader has a _load_single_pack(file), call it.
            if hasattr(self, "_load_single_pack"):
                self._load_single_pack(file)  # type: ignore[attr-defined]
            else:
                # Minimal fallback: call original loader on temp dir containing one file
                # (You can refine this once you confirm your existing structure.)
                pass

    # Monkey-patch the method
    registry_mod.SemanticRegistry.load_packs = load_packs_recursive  # type: ignore[assignment]