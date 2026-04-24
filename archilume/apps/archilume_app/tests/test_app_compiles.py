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
