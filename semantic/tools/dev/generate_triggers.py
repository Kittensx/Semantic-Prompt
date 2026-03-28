import sys
from pathlib import Path

# Add extension root so `import semantic...` works
ROOT_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT_DIR))

from semantic.tools.dev.auto_trigger_builder import generate_triggers, BuildOptions

SEMANTIC_DIR = Path(__file__).resolve().parents[2]  # .../semantic

PACKS_DIRS = [
    SEMANTIC_DIR / "packs",
    SEMANTIC_DIR / "user" / "packs",
]

ADDONS_DIR = SEMANTIC_DIR / "addons"
core_triggers = SEMANTIC_DIR / "triggers" / "triggers.json"

generate_triggers(
    base_dir=SEMANTIC_DIR,
    packs_dirs=PACKS_DIRS,
    addons_dir=ADDONS_DIR,
    existing_triggers_path=core_triggers,
    out_generated_path=SEMANTIC_DIR / "triggers" / "triggers.generated.json",
    out_conflicts_path=SEMANTIC_DIR / "triggers" / "trigger_conflicts.generated.json",
    out_report_path=SEMANTIC_DIR / "triggers" / "trigger_report.generated.md",
    opts=BuildOptions(
        include_keys=True,
        include_aliases=True,
        skip_examples=True,
    ),
    keep_multi_category=False,
    prefer_existing=True,
)

print("Done. Wrote triggers.generated.json")