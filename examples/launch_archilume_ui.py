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

_CHROME_NAMES = [
    "chrome",
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
]

_CHROME_WIN_PATHS = [
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
]


def _get_browser() -> webbrowser.BaseBrowser:
    """Return a Chrome browser controller if available, else the default."""
    # Try named registrations first (works on Linux/macOS after PATH lookup)
    for name in _CHROME_NAMES:
        try:
            b = webbrowser.get(name)
            if b is not None:
                return b
        except webbrowser.Error:
            pass

    # On Windows, look for chrome.exe at known install paths
    if sys.platform == "win32":
        for chrome_path in _CHROME_WIN_PATHS:
            if chrome_path.exists():
                webbrowser.register("chrome", None, webbrowser.BackgroundBrowser(str(chrome_path)))
                return webbrowser.get("chrome")

    # Fall back to the OS default
    return webbrowser.get()


def _open_browser_when_ready(proc: subprocess.Popen) -> None:
    """Watch stdout for the Reflex 'App running' signal then open the browser."""
    if proc.stdout is None:
        return
    browser = _get_browser()
    for line in proc.stdout:
        print(line, end="", flush=True)
        if "App running" in line or "localhost:3000" in line:
            browser.open(URL)
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
