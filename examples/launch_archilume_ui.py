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

_REFLEX_BACKEND_PORTS = range(8000, 8020)


def _kill_stale_backends() -> None:
    """Kill any processes holding Reflex backend ports and wait for OS to release them."""
    import concurrent.futures
    import socket
    import time

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
        def _fuser_kill(port: int) -> None:
            subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True)

        with concurrent.futures.ThreadPoolExecutor() as ex:
            ex.map(_fuser_kill, _REFLEX_BACKEND_PORTS)

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
    import socket
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

    print("Cleaning up stale Reflex backend processes...")
    _kill_stale_backends()
    print(f"Launching Archilume UI from: {app_dir}")
    print(f"Browser will open automatically at {URL}")
    os.chdir(app_dir)

    free_port = _find_free_port()
    print(f"Using backend port: {free_port}")
    env = os.environ.copy()
    env["API_URL"] = f"http://localhost:{free_port}"
    proc = subprocess.Popen(
        [sys.executable, "-m", "reflex", "run", "--env", "dev", "--backend-port", str(free_port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )

    t = threading.Thread(target=_open_browser_when_ready, args=(proc,), daemon=True)
    t.start()

    proc.wait()
