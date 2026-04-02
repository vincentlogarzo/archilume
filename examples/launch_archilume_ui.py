"""Launch the Reflex-based Archilume UI editor.

Run from the archilume_ui app directory:
    cd archilume/apps/archilume_ui
    reflex run

Or use this script which changes directory and launches:
    python examples/launch_archilume_ui.py
"""

import os
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    app_dir = Path(__file__).resolve().parent.parent / "archilume" / "apps" / "archilume_ui"
    if not app_dir.exists():
        print(f"App directory not found: {app_dir}")
        sys.exit(1)

    print(f"Launching Archilume UI from: {app_dir}")
    print("Open http://localhost:3000 in your browser")
    print("Note: font/style changes require a full restart (Ctrl+C then re-run)")
    os.chdir(app_dir)
    subprocess.run([sys.executable, "-m", "reflex", "run", "--env", "dev"], check=True)
