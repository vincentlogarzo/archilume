"""Repo-root pytest configuration and shared fixtures.

Keeps sys.path wiring in one place and factors the Reflex-state construction
boilerplate that several app-level tests duplicate (see
``test_overlay_level_keying._make_state``, ``test_room_hierarchy._make_state``,
etc.) into a single ``make_editor_state`` fixture.

Also exposes reusable fixtures for:

* ``temp_project`` — a populated ``projects/<name>/`` tree backed by
  ``tmp_path``, used by workflow and export-pipeline tests.
* ``mock_gcloud`` — patches ``subprocess.run`` to return canned ``gcloud``
  output, avoiding any real GCP calls.
* ``mock_radiance`` — same pattern for Radiance binaries (``oconv``,
  ``rpict``, ``obj2rad``, ``gensky``, ``pcomb``, ``falsecolor``).

Existing tests that roll their own state boilerplate keep working — the new
fixture is additive.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

# Make the archilume_app package importable from repo root without installing.
_APP_ROOT = Path(__file__).parent / "archilume" / "apps" / "archilume_app"
if _APP_ROOT.exists() and str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))


# ---------------------------------------------------------------- EditorState

_BACKEND_VAR_LIST_KEYS = {"_overlay_undo_stack", "_undo_stack", "_redo_stack"}
_BACKEND_VAR_DICT_KEYS = {"_overlay_session_start"}


def _init_backend_vars(state: Any) -> dict[str, Any]:
    """Build a fresh ``_backend_vars`` dict with sensible defaults per key.

    Mirrors the pattern already used in
    ``test_overlay_level_keying._make_state`` so Reflex's ``__setattr__`` can
    write underscore-prefixed vars without ``AttributeError``.
    """
    bvars: dict[str, Any] = {}
    cls = type(state)
    for key in getattr(cls, "backend_vars", ()):
        if key in _BACKEND_VAR_LIST_KEYS:
            bvars[key] = []
        elif key in _BACKEND_VAR_DICT_KEYS:
            bvars[key] = {}
        else:
            bvars[key] = None
    return bvars


@pytest.fixture
def make_editor_state() -> Callable[..., Any]:
    """Factory fixture that builds an ``EditorState`` bypassing Reflex init.

    Reflex's ``__init__`` runs a heavy dirty-var setup and wires up websocket
    callbacks that aren't available in unit tests. The existing pattern across
    app tests is ``object.__new__(EditorState)`` + manual attribute writes —
    this factory centralises it.

    Usage::

        def test_something(make_editor_state):
            state = make_editor_state(rooms=[...], current_hdr_idx=0)
            state.some_event_handler()
            assert state.rooms == [...]

    The factory installs no-op stubs for ``_auto_save``, ``_push_overlay_undo``
    and ``_rasterize_current_page`` so event handlers that call these during
    normal operation don't blow up. Override via kwargs if a test needs them.
    """
    try:
        from archilume_app.state.editor_state import EditorState  # type: ignore
    except Exception as exc:  # pragma: no cover - import guard
        pytest.skip(f"EditorState not importable: {exc}")

    def _factory(**overrides: Any) -> Any:
        state = object.__new__(EditorState)
        # Reflex-internal bookkeeping.
        object.__setattr__(state, "dirty_vars", set())
        object.__setattr__(state, "_self_dirty_computed_vars", set())
        object.__setattr__(state, "base_state", state)
        object.__setattr__(state, "_backend_vars", _init_backend_vars(state))
        # No-op stubs for side-effecting callbacks.
        object.__setattr__(state, "_auto_save", lambda: None)
        object.__setattr__(state, "_push_overlay_undo", lambda *a, **kw: None)
        object.__setattr__(state, "_rasterize_current_page", lambda *a, **kw: None)
        for key, value in overrides.items():
            setattr(state, key, value)
        return state

    return _factory


# ------------------------------------------------------------- project layout


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Yield a minimal but realistic ``projects/<name>/`` directory tree.

    Layout::

        tmp_path/projects/test_project/
            project.toml
            inputs/
            outputs/image/
            outputs/tiff/
            outputs/wpd/
            aoi/
            hdr/

    The ``project.toml`` contains the two-mode schema defaults. Tests that
    exercise mode-specific branches can overwrite the file or add files
    directly.
    """
    project = tmp_path / "projects" / "test_project"
    for sub in ("inputs", "outputs/image", "outputs/tiff", "outputs/wpd", "aoi", "hdr"):
        (project / sub).mkdir(parents=True, exist_ok=True)
    (project / "project.toml").write_text(
        '[project]\n'
        'name = "test_project"\n'
        'schema_version = 5\n'
        'mode = "sunlight"\n'
        '[paths]\n'
        'pdf_path = ""\n'
        'image_dir = "hdr"\n',
        encoding="utf-8",
    )
    return project


# -------------------------------------------------------- subprocess patchers


class _FakeCompletedProcess:
    """Stand-in for ``subprocess.CompletedProcess`` with the attrs most
    callers read (``stdout``, ``stderr``, ``returncode``)."""

    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode

    def check_returncode(self) -> None:
        if self.returncode != 0:
            raise subprocess.CalledProcessError(self.returncode, "mocked")


@pytest.fixture
def mock_gcloud(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Monkeypatch ``subprocess.run`` so any ``gcloud`` invocation returns a
    canned response. Tests install per-command responses via the returned
    setter::

        def test_list_vms(mock_gcloud):
            mock_gcloud(stdout=json.dumps([{"name": "vm1", "status": "RUNNING"}]))
            ...

    Default is empty stdout, returncode 0.
    """
    state: dict[str, Any] = {"stdout": "", "stderr": "", "returncode": 0}

    def _setter(stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        state["stdout"] = stdout
        state["stderr"] = stderr
        state["returncode"] = returncode

    real_run = subprocess.run

    def _fake_run(cmd: Any, *args: Any, **kwargs: Any):
        argv = cmd if isinstance(cmd, (list, tuple)) else [cmd]
        first = str(argv[0]) if argv else ""
        if "gcloud" in first.lower():
            return _FakeCompletedProcess(state["stdout"], state["stderr"], state["returncode"])
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    return _setter


@pytest.fixture
def mock_radiance(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[list[str]]]:
    """Capture Radiance binary invocations without executing them.

    Intercepts any ``subprocess.run`` whose first token matches a Radiance
    binary name (``oconv``, ``rpict``, ``rtpict``, ``rtrace``, ``obj2rad``,
    ``gensky``, ``pcomb``, ``falsecolor``, ``accelerad_rpict``). Returns a
    dict mapping binary name to the list of argv lists captured during the
    test, so callers can assert on command construction.
    """
    radiance_bins = {
        "oconv", "rpict", "rtpict", "rtrace", "obj2rad", "gensky",
        "pcomb", "falsecolor", "accelerad_rpict", "ra_tiff", "ra_ppm",
    }
    captured: dict[str, list[list[str]]] = {b: [] for b in radiance_bins}

    real_run = subprocess.run

    def _fake_run(cmd: Any, *args: Any, **kwargs: Any):
        argv = list(cmd) if isinstance(cmd, (list, tuple)) else [str(cmd)]
        first = Path(str(argv[0])).name.lower() if argv else ""
        first = first.replace(".exe", "")
        if first in radiance_bins:
            captured[first].append([str(a) for a in argv])
            return _FakeCompletedProcess("", "", 0)
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    return captured


# ---------------------------------------------------------------- misc helpers


@pytest.fixture
def write_json(tmp_path: Path) -> Callable[[str, Any], Path]:
    """Write arbitrary JSON to ``tmp_path/<name>`` and return the path."""

    def _write(name: str, payload: Any) -> Path:
        path = tmp_path / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    return _write
