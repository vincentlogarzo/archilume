"""Launch the Reflex-based Archilume app editor.

Usage:
    python examples/launch_archilume_app.py                   # normal launch
    python examples/launch_archilume_app.py --ensure          # reuse running dev server
    python examples/launch_archilume_app.py --fast            # skip compile + cleanup
    python examples/launch_archilume_app.py --force-compile   # force full recompile
"""

import argparse
import concurrent.futures
import hashlib
import importlib.metadata
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

# Make `archilume` importable when running this script directly from examples/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from archilume import config  # noqa: E402

# --- Constants ---
_REFLEX_BACKEND_PORTS = range(8000, 8020)
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


def _port_free(port: int) -> bool:
    """Return True if *port* is bindable on 0.0.0.0.

    Does NOT use SO_REUSEADDR — result matches what Reflex itself will see.
    Shared by _find_free_port and _kill_stale_backends.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


def _compute_mtime_fingerprint(app_dir: Path) -> str:
    """Hash mtimes of all .py files under app_dir/archilume_app plus rxconfig.py.

    Shared by _should_skip_compile and _write_compile_fingerprint.
    """
    src_dir = app_dir / "archilume_app"
    entries: list[str] = []
    for py_file in sorted(src_dir.rglob("*.py")):
        try:
            entries.append(f"{py_file.relative_to(src_dir)}:{py_file.stat().st_mtime_ns}")
        except OSError:
            entries.append(f"{py_file.relative_to(src_dir)}:missing")
    fp = hashlib.sha256("\n".join(entries).encode()).hexdigest()[:16]
    rxconfig = app_dir / "rxconfig.py"
    if rxconfig.exists():
        fp += f":{rxconfig.stat().st_mtime_ns}"
    return fp


def _should_skip_compile(app_dir: Path) -> bool:
    """Return True if .web/ is up-to-date and compilation can be skipped."""
    reflex_json = app_dir / ".web" / "reflex.json"
    fingerprint_file = app_dir / ".web" / ".archilume_compile_fingerprint"
    if not reflex_json.exists() or not fingerprint_file.exists():
        return False
    try:
        meta = json.loads(reflex_json.read_text(encoding="utf-8"))
        if meta.get("version") != importlib.metadata.version("reflex"):
            return False
        stored_fp = fingerprint_file.read_text(encoding="utf-8").strip()
        return stored_fp == _compute_mtime_fingerprint(app_dir)
    except Exception:
        return False


def _write_compile_fingerprint(app_dir: Path) -> None:
    """Write the current mtime fingerprint to .web/ for next launch."""
    try:
        (app_dir / ".web" / ".archilume_compile_fingerprint").write_text(
            _compute_mtime_fingerprint(app_dir), encoding="utf-8"
        )
    except OSError:
        pass


def _kill_stale_backends() -> None:
    """Kill any processes holding Reflex backend ports, wait for OS to release them."""
    if sys.platform == "win32":
        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
        pids: set[str] = set()
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 5 or "LISTENING" not in line:
                continue
            for port in _REFLEX_BACKEND_PORTS:
                if f":{port} " in line or parts[1].endswith(f":{port}"):
                    pids.add(parts[-1])

        def _kill_pid(pid: str) -> str:
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
            return pid

        if not pids:
            print("  No stale backends found.")
            return
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(pids)) as ex:
            for pid in ex.map(_kill_pid, pids):
                print(f"  Killed stale backend PID {pid}")
    else:
        with concurrent.futures.ThreadPoolExecutor() as ex:
            ex.map(lambda port: subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True), _REFLEX_BACKEND_PORTS)

    # Poll backend ports until all free or timeout
    ports_to_check = list(_REFLEX_BACKEND_PORTS)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(ports_to_check)) as ex:
            results = list(ex.map(_port_free, ports_to_check))
        ports_to_check = [p for p, free in zip(ports_to_check, results) if not free]
        if not ports_to_check:
            print("  All backend ports free.")
            return
        time.sleep(0.1)
    print(f"  Warning: ports {ports_to_check} still in use after 15s — Reflex may skip ahead")


def _find_free_port() -> int:
    """Return the first bindable port in the Reflex backend range."""
    for port in _REFLEX_BACKEND_PORTS:
        if _port_free(port):
            return port
    raise RuntimeError(f"No free port found in range {_REFLEX_BACKEND_PORTS}")


def _is_serving(port: int = 3000, timeout: float = 2.0) -> bool:
    """Return True if localhost:port responds with HTTP 200."""
    try:
        resp = urllib.request.urlopen(f"http://localhost:{port}", timeout=timeout)
        return resp.status == 200
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def _open_browser_when_ready() -> None:
    """Poll localhost:3000 with exponential backoff (0.1s → 1s cap), open browser when ready."""

    def _get_browser() -> webbrowser.BaseBrowser:
        """Return a Chrome browser controller if available, else the default."""
        for name in _CHROME_NAMES:
            try:
                return webbrowser.get(name)
            except webbrowser.Error:
                pass
        if sys.platform == "win32":
            for chrome_path in _CHROME_WIN_PATHS:
                if chrome_path.exists():
                    webbrowser.register("chrome", None, webbrowser.BackgroundBrowser(str(chrome_path)))
                    return webbrowser.get("chrome")
        return webbrowser.get()

    deadline = time.monotonic() + 120
    interval = 0.1
    while time.monotonic() < deadline:
        if _is_serving():
            _get_browser().open(URL)
            return
        time.sleep(interval)
        interval = min(interval * 1.3, 1.0)
    print("Warning: UI did not become ready within timeout — browser not opened.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Launch the Archilume app dev server.")
    parser.add_argument("--ensure", action="store_true",
                        help="Reuse an already-running dev server if :3000 is serving.")
    parser.add_argument("--project", default="527DP-gcloud-lowRes-GregW",
                        help="Project name to open automatically on load.")
    parser.add_argument("--fast", action="store_true",
                        help="Skip compile and cleanup for fastest possible restart.")
    parser.add_argument("--force-compile", action="store_true",
                        help="Force a full recompile even if code appears unchanged.")
    args = parser.parse_args()

    if args.ensure and _is_serving():
        print(f"UI already running at {URL}")
        sys.exit(0)

    app_dir = config.ARCHILUME_APP_DIR
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

    print(f"Launching Archilume app from: {app_dir}")
    print(f"Browser will open automatically at {URL}")
    os.chdir(app_dir)

    try:
        free_port = _find_free_port()
    except RuntimeError:
        if not args.fast:
            raise
        print("No free port — falling back to stale backend cleanup...")
        _kill_stale_backends()
        free_port = _find_free_port()
    print(f"Using backend port: {free_port}")
    env["API_URL"] = f"http://localhost:{free_port}"
    if args.project:
        env["ARCHILUME_INITIAL_PROJECT"] = args.project
        print(f"Auto-opening project: {args.project}")
    proc = subprocess.Popen(
        [sys.executable, "-m", "reflex", "run", "--env", "dev", "--backend-port", str(free_port)],
        env=env,
    )

    threading.Thread(target=_open_browser_when_ready, daemon=True).start()
    proc.wait()
    _write_compile_fingerprint(app_dir)