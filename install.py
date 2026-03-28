import importlib
import subprocess
import sys
from pathlib import Path

REQUIREMENTS_FILE = Path(__file__).parent / "requirements.txt"

# modules to test import for
REQUIRED_MODULES = [
    "sqlite3",   # stdlib
    "gradio",
]

# Path to your bat file (inside semantic/)
INSTALL_BAT = Path(__file__).parent / "semantic" / "install_packs_from_database.bat"


def missing_modules():
    missing = []
    for module in REQUIRED_MODULES:
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(module)
    return missing


def install_requirements():
    if not REQUIREMENTS_FILE.exists():
        print("[semantic_prompt] requirements.txt not found.")
        return

    print("[semantic_prompt] Installing missing dependencies...")
    subprocess.check_call([
        sys.executable,
        "-m",
        "pip",
        "install",
        "-r",
        str(REQUIREMENTS_FILE)
    ])


def run_install_bat():
    if not INSTALL_BAT.exists():
        print(f"[semantic_prompt] install bat not found: {INSTALL_BAT}")
        return

    print("[semantic_prompt] Running pack installer...")
    try:
        subprocess.check_call(
            ["cmd", "/c", str(INSTALL_BAT)],
            cwd=INSTALL_BAT.parent  # IMPORTANT: run inside semantic/
        )
    except subprocess.CalledProcessError as e:
        print("[semantic_prompt] Pack install failed.")
        raise e


def main():
    missing = missing_modules()

    if missing:
        print(f"[semantic_prompt] Missing modules: {', '.join(missing)}")
        install_requirements()

    # Always run pack install (safe because your bat uses --backup)
    run_install_bat()


if __name__ == "__main__":
    main()