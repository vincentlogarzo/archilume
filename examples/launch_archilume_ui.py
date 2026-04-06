"""Launch the Reflex-based Archilume UI editor.

Run from the archilume_ui app directory:
    cd archilume/apps/archilume_ui
    reflex run

Run from docker image:
    docker run -p 3000:3000 -p 8000:8000 -v C:/Projects/test-archilume/projects:/app/projects vlogarzo/archilume-ui

Or use this script which changes directory and launches:
    python examples/launch_archilume_ui.py
"""

import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

URL = "http://localhost:3000"


def _open_browser_when_ready(proc: subprocess.Popen) -> None:
    """Watch stdout for the Reflex 'App running' signal then open the browser."""
    if proc.stdout is None:
        return
    for line in proc.stdout:
        print(line, end="", flush=True)
        if "App running" in line or "localhost:3000" in line:
            webbrowser.open(URL)
            break
    for line in proc.stdout:
        print(line, end="", flush=True)


if __name__ == "__main__":
    app_dir = Path(__file__).resolve().parent.parent / "archilume" / "apps" / "archilume_ui"
    if not app_dir.exists():
        print(f"App directofry not found: {app_dir}")
        sys.exit(1)

    print(f"Launching Archilume UI from: {app_dir}")
    print(f"Browser will open automatically at {URL}")
    os.chdir(app_dir)

    proc = subprocess.Popen(
        [sys.executable, "-m", "reflex", "run", "--env", "dev"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    t = threading.Thread(target=_open_browser_when_ready, args=(proc,), daemon=True)
    t.start()

    proc.wait()
