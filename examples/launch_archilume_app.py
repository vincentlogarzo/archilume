"""Launch the Reflex-based Archilume UI editor.

Run from the archilume_ui app directory:
    cd archilume/apps/archilume_ui
    reflex run

Run from docker image:
    docker run -p 3000:3000 -p 8000:8000 -v C:/Projects/test-archilume/projects:/app/projects vlogarzo/archilume-ui

Or use this script which changes directory and launches:
    python examples/launch_archilume_app.py

Pass --ensure to reuse an already-running dev server instead of relaunching:
    python examples/launch_archilume_app.py --ensure

Pass --fast to skip compilation and cleanup (fastest restart when code is unchanged):
    python examples/launch_archilume_app.py --fast

Pass --force-compile to force a full recompile:
    python examples/launch_archilume_app.py --force-compile
"""

import argparse
import concurrent.futures
import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

_REFLEX_BACKEND_PORTS = range(8000, 8020)


def _compute_mtime_fingerprint(src_dir: Path) -> str:
    """Hash the modification times of all .py files under *src_dir*."""
    entries: list[str] = []
    for py_file in sorted(src_dir.rglob("*.py")):
        try:
            entries.append(f"{py_file.relative_to(src_dir)}:{py_file.stat().st_mtime_ns}")
        except OSError:
            entries.append(f"{py_file.relative_to(src_dir)}:missing")
    return hashlib.sha256("\n".join(entries).encode()).hexdigest()[:16]


def _should_skip_compile(app_dir: Path) -> bool:
    """Return True if .web/ is up-to-date and compilation can be skipped."""
    web_dir = app_dir / ".web"
    reflex_json = web_dir / "reflex.json"
    fingerprint_file = web_dir / ".archilume_compile_fingerprint"

    # Compiled output must exist
    if not reflex_json.exists():
        return False

    # Reflex version must match
    try:
        import importlib.metadata
        meta = json.loads(reflex_json.read_text(encoding="utf-8"))
        installed = importlib.metadata.version("reflex")
        if meta.get("version") != installed:
            return False
    except Exception:
        return False

    # Source fingerprint must match
    src_dir = app_dir / "archilume_ui"
    current_fp = _compute_mtime_fingerprint(src_dir)
    # Also include rxconfig.py in the fingerprint
    rxconfig = app_dir / "rxconfig.py"
    if rxconfig.exists():
        current_fp += f":{rxconfig.stat().st_mtime_ns}"

    if fingerprint_file.exists():
        try:
            stored_fp = fingerprint_file.read_text(encoding="utf-8").strip()
            if stored_fp == current_fp:
                return True
        except OSError:
            pass
    return False


def _write_compile_fingerprint(app_dir: Path) -> None:
    """Write the current mtime fingerprint to .web/ for next launch."""
    web_dir = app_dir / ".web"
    fingerprint_file = web_dir / ".archilume_compile_fingerprint"
    src_dir = app_dir / "archilume_ui"
    fp = _compute_mtime_fingerprint(src_dir)
    rxconfig = app_dir / "rxconfig.py"
    if rxconfig.exists():
        fp += f":{rxconfig.stat().st_mtime_ns}"
    try:
        fingerprint_file.write_text(fp, encoding="utf-8")
    except OSError:
        pass


def _kill_stale_backends() -> None:
    """Kill any processes holding Reflex backend ports and wait for OS to release them."""
    if sys.platform == "win32":
        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
        pids: set[str] = set()
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 5 or "LISTENING" not in line:
                continue
            for port in _REFLEX_BACKEND_PORTS:
                if f":{port} " in line or line.split()[1].endswith(f":{port}"):
                    pids.add(parts[-1])

        def _kill_pid(pid: str) -> str:
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
            return pid

        if pids:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(pids)) as ex:
                for pid in ex.map(_kill_pid, pids):
                    print(f"  Killed stale backend PID {pid}")
        else:
            print("  No stale backends found.")
            return
    else:
        with concurrent.futures.ThreadPoolExecutor() as ex:
            ex.map(lambda port: subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True), _REFLEX_BACKEND_PORTS)

    # Poll all backend ports concurrently; unblock as soon as every one is free.
    # Do NOT use SO_REUSEADDR — it masks TIME_WAIT and gives false positives.
    ports_to_check = list(_REFLEX_BACKEND_PORTS)
    deadline = time.monotonic() + 15

    def _port_free(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return True
            except OSError:
                return False

    timed_out = True
    while time.monotonic() < deadline:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(ports_to_check)) as ex:
            results = list(ex.map(_port_free, ports_to_check))
        still_held = [p for p, free in zip(ports_to_check, results) if not free]
        if not still_held:
            print("  All backend ports free.")
            timed_out = False
            break
        ports_to_check = still_held
        time.sleep(0.1)
    if timed_out:
        print(f"  Warning: ports {ports_to_check} still in use after 15s — Reflex may skip ahead")


URL = "http://localhost:3000"


def _find_free_port() -> int:
    """Return the first port in the Reflex backend range that is actually bindable.
    Does NOT use SO_REUSEADDR so the result matches what Reflex itself will see."""
    for port in _REFLEX_BACKEND_PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {_REFLEX_BACKEND_PORTS}")

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


def _is_serving(port: int = 3000, timeout: float = 2.0) -> bool:
    """Return True if localhost:port responds with HTTP 200."""
    try:
        resp = urllib.request.urlopen(f"http://localhost:{port}", timeout=timeout)
        return resp.status == 200
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def _wait_until_ready(port: int = 3000, timeout: int = 120) -> bool:
    """Poll localhost:port until it serves, or timeout expires.

    Uses exponential backoff: starts at 100ms, caps at 1s.
    Returns True when ready, False on timeout.
    """
    deadline = time.monotonic() + timeout
    interval = 0.1
    while time.monotonic() < deadline:
        if _is_serving(port):
            return True
        time.sleep(interval)
        interval = min(interval * 1.3, 1.0)
    return False


def _open_browser_when_ready() -> None:
    """Poll until the frontend is serving, then open the browser."""
    if _wait_until_ready():
        _get_browser().open(URL)
    else:
        print("Warning: UI did not become ready within timeout — browser not opened.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Launch the Archilume UI dev server.")
    parser.add_argument(
        "--ensure",
        action="store_true",
        help="Reuse an already-running dev server if :3000 is serving; skip relaunch.",
    )
    parser.add_argument(
        "--project",
        default="527DP-gcloud-lowRes-GregW",
        help="Project name to open automatically on load (default: 527DP-gcloud-lowRes-GregW).",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Skip compile and cleanup for fastest possible restart (use when code is unchanged).",
    )
    parser.add_argument(
        "--force-compile",
        action="store_true",
        help="Force a full recompile even if code appears unchanged.",
    )
    args = parser.parse_args()

    if args.ensure and _is_serving():
        print(f"UI already running at {URL}")
        sys.exit(0)

    app_dir = Path(__file__).resolve().parent.parent / "archilume" / "apps" / "archilume_ui"
    if not app_dir.exists():
        print(f"App directory not found: {app_dir}")
        sys.exit(1)

    env = os.environ.copy()

    # --- Compile skip logic ---
    if args.fast:
        env["REFLEX_SKIP_COMPILE"] = "1"
        env["REFLEX_PERSIST_WEB_DIR"] = "1"
        print("Fast mode: skipping compile and cleanup")
    elif args.force_compile:
        print("Force compile: full recompile requested")
    elif _should_skip_compile(app_dir):
        env["REFLEX_SKIP_COMPILE"] = "1"
        env["REFLEX_PERSIST_WEB_DIR"] = "1"
        print("Skipping compile (code unchanged)")
    else:
        print("Full compile required (code changed or first run)")

    # --- Stale backend cleanup ---
    if not args.fast:
        print("Cleaning up stale Reflex backend processes...")
        _kill_stale_backends()

    print(f"Launching Archilume UI from: {app_dir}")
    print(f"Browser will open automatically at {URL}")
    os.chdir(app_dir)

    try:
        free_port = _find_free_port()
    except RuntimeError:
        if args.fast:
            print("No free port — falling back to stale backend cleanup...")
            _kill_stale_backends()
            free_port = _find_free_port()
        else:
            raise
    print(f"Using backend port: {free_port}")
    env["API_URL"] = f"http://localhost:{free_port}"
    if args.project:
        env["ARCHILUME_INITIAL_PROJECT"] = args.project
        print(f"Auto-opening project: {args.project}")
    proc = subprocess.Popen(
        [sys.executable, "-m", "reflex", "run", "--env", "dev", "--backend-port", str(free_port)],
        env=env,
    )

    t = threading.Thread(target=_open_browser_when_ready, daemon=True)
    t.start()

    proc.wait()
    _write_compile_fingerprint(app_dir)
