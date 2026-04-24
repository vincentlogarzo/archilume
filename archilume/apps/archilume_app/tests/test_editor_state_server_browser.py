"""Tests for the server-side file browser deployment-mode behaviour.

Covers the three deployment modes (``native`` / ``local-docker`` / ``hosted``)
driven by ``ARCHILUME_DEPLOYMENT_MODE``:

- ``open_external_browser`` roots at ``PROJECTS_DIR``.
- ``external_browser_go_up`` and ``external_browser_navigate`` refuse to
  step above the clamp root (security on hosted, hygiene on local-docker).
- ``pick_create_field_file`` skips the tkinter dialog in Docker and routes
  straight into the server-side browser.
- ``show_server_browse`` / ``external_browser_at_root`` /
  ``external_browser_display_path`` computed vars drive UI gating.

Note: the EditorState class is registered globally with Reflex at import
time, so we cannot reload the editor_state module between tests. Instead
we monkeypatch ``archilume.config`` module attributes directly; every
helper reads ``DEPLOYMENT_MODE`` / ``PROJECTS_DIR`` / ``HOST_PROJECTS_DIR``
at call time so the patches take effect immediately.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def _patch_config(monkeypatch, **kwargs):
    import archilume.config as cfg  # type: ignore
    for k, v in kwargs.items():
        monkeypatch.setattr(cfg, k, v, raising=False)


# ================================================================ clamp logic


class TestClampRoot:
    def test_path_within_root_inside(self, make_editor_state, tmp_path):
        s = make_editor_state(external_browser_root=str(tmp_path))
        assert s._path_within_root(tmp_path / "cowles")

    def test_path_within_root_at_root(self, make_editor_state, tmp_path):
        s = make_editor_state(external_browser_root=str(tmp_path))
        assert s._path_within_root(tmp_path)

    def test_path_within_root_outside(self, make_editor_state, tmp_path):
        s = make_editor_state(external_browser_root=str(tmp_path / "a"))
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        assert not s._path_within_root(tmp_path / "b")

    def test_empty_root_disables_clamp(self, make_editor_state, tmp_path):
        s = make_editor_state(external_browser_root="")
        assert s._path_within_root(Path("/etc"))

    def test_go_up_refuses_above_root(self, make_editor_state, tmp_path):
        root = tmp_path / "projects"
        root.mkdir()
        s = make_editor_state(
            external_browser_root=str(root),
            external_browser_path=str(root),
            external_browser_entries=[],
        )
        s.external_browser_go_up()
        assert s.external_browser_path == str(root)

    def test_navigate_rejects_outside_root(self, make_editor_state, tmp_path):
        root = tmp_path / "projects"
        root.mkdir()
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        s = make_editor_state(
            external_browser_root=str(root),
            external_browser_path=str(root),
            external_browser_entries=[],
        )
        s.external_browser_navigate(str(outside))
        assert s.external_browser_path == str(root)
        assert "Outside" in s.external_browser_error


# ========================================================= deployment gating


class TestDeploymentGating:
    def test_show_server_browse_hidden_on_hosted(self, monkeypatch, make_editor_state):
        _patch_config(monkeypatch, DEPLOYMENT_MODE="hosted")
        s = make_editor_state()
        assert s.show_server_browse is False

    def test_show_server_browse_visible_on_native(self, monkeypatch, make_editor_state):
        _patch_config(monkeypatch, DEPLOYMENT_MODE="native")
        s = make_editor_state()
        assert s.show_server_browse is True

    def test_show_server_browse_visible_on_local_docker(
        self, monkeypatch, make_editor_state
    ):
        _patch_config(monkeypatch, DEPLOYMENT_MODE="local-docker")
        s = make_editor_state()
        assert s.show_server_browse is True

    def test_deployment_is_native_helper(self, monkeypatch):
        from archilume_app.state.editor_state import _deployment_is_native  # type: ignore

        _patch_config(monkeypatch, DEPLOYMENT_MODE="local-docker")
        assert _deployment_is_native() is False

        _patch_config(monkeypatch, DEPLOYMENT_MODE="native")
        assert _deployment_is_native() is True


# ===================================================== computed vars for UI


class TestBrowserComputedVars:
    def test_at_root_true(self, make_editor_state, tmp_path):
        s = make_editor_state(
            external_browser_root=str(tmp_path),
            external_browser_path=str(tmp_path),
        )
        assert s.external_browser_at_root is True

    def test_at_root_false_when_deeper(self, make_editor_state, tmp_path):
        sub = tmp_path / "cowles"
        sub.mkdir()
        s = make_editor_state(
            external_browser_root=str(tmp_path),
            external_browser_path=str(sub),
        )
        assert s.external_browser_at_root is False

    def test_display_path_passthrough_when_host_equals_container(
        self, monkeypatch, make_editor_state, tmp_path
    ):
        _patch_config(
            monkeypatch,
            PROJECTS_DIR=tmp_path,
            HOST_PROJECTS_DIR=str(tmp_path),
        )
        s = make_editor_state(external_browser_path=str(tmp_path / "cowles"))
        assert s.external_browser_display_path == str(tmp_path / "cowles")

    def test_display_path_substitutes_host_prefix(
        self, monkeypatch, make_editor_state, tmp_path
    ):
        # Use real tmp_path as the container root so str(Path) round-trips on
        # every OS. Only the *mapping* logic is under test here.
        container = tmp_path / "container_projects"
        container.mkdir()
        host = r"C:\x\projects" if os.name == "nt" else "/home/u/projects"
        _patch_config(
            monkeypatch,
            PROJECTS_DIR=container,
            HOST_PROJECTS_DIR=host,
        )
        s = make_editor_state(external_browser_path=str(container / "cowles"))
        result = s.external_browser_display_path
        assert result.startswith(host)
        assert "cowles" in result


# ===================================================== pick_create_field_file


class TestPickCreateFieldFile:
    """In non-native mode, ``pick_create_field_file`` must skip the tkinter
    branch and route straight into ``open_create_file_browser``."""

    def test_non_native_opens_server_browser(
        self, monkeypatch, make_editor_state, tmp_path
    ):
        _patch_config(
            monkeypatch, DEPLOYMENT_MODE="local-docker", PROJECTS_DIR=tmp_path
        )

        import builtins
        real_import = builtins.__import__

        def _no_tk(name, *args, **kwargs):
            if name.startswith("tkinter"):
                raise AssertionError("tkinter imported in local-docker mode")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_tk)

        s = make_editor_state(new_project_mode="sunlight")
        s.pick_create_field_file("pdf")
        assert s.external_browser_open is True
        assert s.external_browser_mode == "create_file"
        assert s.external_browser_target_field == "pdf"
        assert s.external_browser_root == str(tmp_path)

    def test_unknown_field_returns_toast(
        self, monkeypatch, make_editor_state, tmp_path
    ):
        _patch_config(
            monkeypatch, DEPLOYMENT_MODE="local-docker", PROJECTS_DIR=tmp_path
        )
        s = make_editor_state(
            new_project_mode="sunlight",
            external_browser_open=False,
        )
        result = s.pick_create_field_file("not_a_field")
        # rx.toast.error returns an event spec — confirm non-None and browser
        # stayed closed.
        assert result is not None
        assert s.external_browser_open is False


# ===================================================== open_external_browser


class TestOpenExternalBrowser:
    def test_roots_at_projects_dir(self, monkeypatch, make_editor_state, tmp_path):
        _patch_config(monkeypatch, PROJECTS_DIR=tmp_path)
        s = make_editor_state()
        s.open_external_browser()
        assert s.external_browser_path == str(tmp_path)
        assert s.external_browser_root == str(tmp_path)
        assert s.external_browser_mode == "project"
        assert s.external_browser_open is True


# =================================================== external_browser_select


class TestSelectStagedFile:
    """``external_browser_select`` dispatches on mode — ``settings_file`` and
    ``create_file`` both stage into the matching target flow."""

    def test_create_file_mode_stages_into_create(
        self, monkeypatch, make_editor_state, tmp_path
    ):
        _patch_config(monkeypatch, PROJECTS_DIR=tmp_path)
        pdf_file = tmp_path / "plan.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy")

        s = make_editor_state(
            new_project_mode="sunlight",
            new_project_staging_dir=str(tmp_path / "staging"),
            external_browser_root=str(tmp_path),
            external_browser_path=str(tmp_path),
            external_browser_mode="create_file",
            external_browser_target_field="pdf",
            external_browser_allowed_extensions=[".pdf"],
            external_browser_multiple=False,
            external_browser_open=True,
        )
        # Replace _stage_uploaded_files on the class so a bound call from
        # ``external_browser_select`` -> ``_select_staged_browser_file`` lands
        # here. Accepting ``self`` keeps the signature aligned with the real
        # method.
        captured = {}

        def _fake_stage(self, field_id, files, target):
            captured["field_id"] = field_id
            captured["target"] = target
            captured["count"] = len(files)

        monkeypatch.setattr(type(s), "_stage_uploaded_files", _fake_stage)
        s.external_browser_select(str(pdf_file))
        assert captured["target"] == "create"
        assert captured["field_id"] == "pdf"
        assert captured["count"] == 1
        assert s.external_browser_open is False

    def test_select_outside_root_refused(
        self, monkeypatch, make_editor_state, tmp_path
    ):
        _patch_config(monkeypatch, PROJECTS_DIR=tmp_path)
        root = tmp_path / "projects"
        root.mkdir()
        outside_file = tmp_path / "evil.pdf"
        outside_file.write_bytes(b"%PDF-1.4 dummy")

        s = make_editor_state(
            new_project_mode="sunlight",
            external_browser_root=str(root),
            external_browser_path=str(root),
            external_browser_mode="create_file",
            external_browser_target_field="pdf",
            external_browser_allowed_extensions=[".pdf"],
            external_browser_multiple=False,
        )
        called = {"n": 0}

        def _fake_stage(self, *args, **kwargs):
            called["n"] += 1

        monkeypatch.setattr(type(s), "_stage_uploaded_files", _fake_stage)
        s.external_browser_select(str(outside_file))
        assert called["n"] == 0
        assert "Outside" in s.external_browser_error
