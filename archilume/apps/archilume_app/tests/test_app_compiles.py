"""Guard against Reflex compile-time AttributeErrors.

The archilume_app fails to start when a component references an
``EditorState.X`` attribute that was never added to the state class — the
error surfaces only during page compilation, which normally happens after
``reflex run`` spawns a worker process. This test runs the same compile path
in-process so CI catches the bug before the user does.

Any new component reference to ``EditorState`` / ``S`` aliases must resolve
against state/editor_state.py for this test to pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.integration
def test_app_dry_compiles(monkeypatch: pytest.MonkeyPatch) -> None:
    app_dir = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(app_dir)

    from archilume_app.archilume_app import app

    app._compile(dry_run=True)


def test_browser_error_bridge_present() -> None:
    """The error/console bridge must remain wired into _ZOOM_GUARD_SCRIPT.

    Catches accidental edits that drop the listeners — without this guard,
    JS errors would silently disappear and the unified-log promise breaks.
    """
    from archilume_app.archilume_app import _ZOOM_GUARD_SCRIPT

    src = str(_ZOOM_GUARD_SCRIPT)
    assert "addEventListener('error'" in src
    assert "addEventListener('unhandledrejection'" in src
    assert "js_error" in src
    assert "js_unhandled_rejection" in src
    assert "js_console" in src
    # console.error and console.warn must be patched, console.log must not.
    assert "console.log" not in src or "_patchConsole" in src
