"""Tests for full-reload project switching.

``EditorState.open_project`` no longer mutates state in place — it persists the
outgoing session and returns an ``rx.redirect`` that forces a browser reload
with ``?project=NAME``. The fresh page then boots through ``init_on_load``,
which reads the query param, clears process-scoped caches, and delegates to
``_open_project_progressive``.

These tests verify the redirect contract and the cache-clearing side effect.
"""

from __future__ import annotations

from unittest.mock import patch

from archilume_app.lib import image_loader
from archilume_app.state import editor_state as es_mod
from archilume_app.state.editor_state import EditorState


def _make_minimal_state() -> EditorState:
    """Construct an EditorState with just enough plumbing to call open_project.

    Bypasses Reflex __init__ the same way tests/test_overlay_level_keying.py does.
    """
    state = object.__new__(EditorState)
    object.__setattr__(state, "dirty_vars", set())
    object.__setattr__(state, "_self_dirty_computed_vars", set())
    object.__setattr__(state, "base_state", state)
    _bvars: dict = {k: None for k in EditorState.backend_vars}
    object.__setattr__(state, "_backend_vars", _bvars)
    return state


def _redirect_args(event_spec) -> dict[str, object]:
    """Flatten ``rx.redirect(...).args`` into a ``{kw: value}`` dict."""
    out: dict[str, object] = {}
    for key_var, value_var in event_spec.args:
        out[key_var._js_expr] = getattr(value_var, "_var_value", None)
    return out


# ---------------------------------------------------------------------------
# open_project → redirect contract
# ---------------------------------------------------------------------------


class TestOpenProjectRedirect:
    def test_returns_redirect_with_query_param(self):
        state = _make_minimal_state()
        with patch.object(EditorState, "save_session", lambda self: None):
            result = state.open_project("MyProj")

        args = _redirect_args(result)
        assert args["path"] == "/?project=MyProj"
        assert args["external"] is True

    def test_url_encodes_name_with_spaces_and_symbols(self):
        state = _make_minimal_state()
        with patch.object(EditorState, "save_session", lambda self: None):
            result = state.open_project("My Project (v2)")

        args = _redirect_args(result)
        # safe='' forces slashes and parens to encode too
        assert args["path"] == "/?project=My%20Project%20%28v2%29"
        assert args["external"] is True

    def test_empty_name_is_noop(self):
        state = _make_minimal_state()
        result = state.open_project("")
        assert result is None

    def test_save_session_failure_does_not_block_redirect(self):
        """If save_session raises, open_project still returns the redirect so
        the user isn't stranded in a corrupted session."""
        state = _make_minimal_state()

        def raising_save(self):
            raise RuntimeError("disk full")

        with patch.object(EditorState, "save_session", raising_save):
            result = state.open_project("NextProj")

        args = _redirect_args(result)
        assert args["path"] == "/?project=NextProj"
        assert args["external"] is True


# ---------------------------------------------------------------------------
# image_loader.clear_cache clears all four module caches
# ---------------------------------------------------------------------------


class TestImageLoaderClearCache:
    def test_clears_image_cache(self):
        image_loader._image_cache["fake/path.hdr"] = "b64-data"
        image_loader.clear_cache()
        assert len(image_loader._image_cache) == 0

    def test_clears_hdr_params_cache(self):
        image_loader._hdr_params_cache["fake/path.hdr"] = (123.0, object())
        image_loader.clear_cache()
        assert image_loader._hdr_params_cache == {}

    def test_clears_scan_hdr_files_cache(self):
        image_loader._scan_hdr_files_cache["fake/dir"] = (123.0, [])
        image_loader.clear_cache()
        assert image_loader._scan_hdr_files_cache == {}

    def test_clears_view_groups_cache(self):
        image_loader._view_groups_cache["fake/dir"] = (123.0, [])
        image_loader.clear_cache()
        assert image_loader._view_groups_cache == {}

    def test_all_four_in_one_call(self):
        image_loader._image_cache["a"] = "1"
        image_loader._hdr_params_cache["b"] = (1.0, None)
        image_loader._scan_hdr_files_cache["c"] = (1.0, [])
        image_loader._view_groups_cache["d"] = (1.0, [])

        image_loader.clear_cache()

        assert len(image_loader._image_cache) == 0
        assert image_loader._hdr_params_cache == {}
        assert image_loader._scan_hdr_files_cache == {}
        assert image_loader._view_groups_cache == {}


# ---------------------------------------------------------------------------
# _df_cache reset contract (init_on_load responsibility)
# ---------------------------------------------------------------------------


class TestDfCacheReset:
    def test_df_cache_holds_expected_shape(self):
        """init_on_load writes back this exact shape; codify the contract so
        a rename of the cache keys breaks loudly."""
        assert "hdr_path" in es_mod._df_cache
        assert "image" in es_mod._df_cache

    def test_reset_shape_is_safe(self):
        """The reset assignment in init_on_load must not raise."""
        original = dict(es_mod._df_cache)
        try:
            es_mod._df_cache["image"] = None
            es_mod._df_cache["hdr_path"] = ""
            assert es_mod._df_cache["image"] is None
            assert es_mod._df_cache["hdr_path"] == ""
        finally:
            es_mod._df_cache.update(original)
