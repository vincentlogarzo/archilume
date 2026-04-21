"""Structural smoke tests for Reflex components.

Each component builder returns an ``rx.Component`` tree. These tests check
that:

1. The builder can be imported and called without error.
2. The returned object is an ``rx.Component`` (so the SVG/HTML composition
   is at least structurally valid).
3. Builders that take no arguments work from a clean state.

No runtime rendering or browser interaction is simulated — that is out of
scope for unit tests. This catches regressions where a component references
a renamed ``EditorState`` var, imports a non-existent helper, or breaks the
``rx.el.*`` surface.
"""

from __future__ import annotations

import reflex as rx
import pytest


def _assert_component(c: object) -> None:
    assert isinstance(c, rx.Component), f"expected rx.Component, got {type(c)!r}"


# =========================================================================
# header.py
# =========================================================================


class TestHeader:
    def test_header_returns_component(self):
        from archilume_app.components.header import header
        _assert_component(header())

    def test_tab_btn_returns_component(self):
        from archilume_app.components.header import _tab_btn
        _assert_component(_tab_btn("viewer", "Viewer", "image"))

    def test_mode_badge_returns_component(self):
        from archilume_app.components.header import _mode_badge
        _assert_component(_mode_badge("EDIT", "#fff", "#000", "#f00", visible=True))


# =========================================================================
# sidebar.py
# =========================================================================


class TestSidebar:
    def test_sidebar_returns_component(self):
        from archilume_app.components.sidebar import sidebar
        _assert_component(sidebar())

    def test_divider_returns_component(self):
        from archilume_app.components.sidebar import _divider
        _assert_component(_divider())


# =========================================================================
# frame_playback_bar.py
# =========================================================================


class TestFramePlaybackBar:
    def test_frame_playback_bar_returns_component(self):
        from archilume_app.components.frame_playback_bar import frame_playback_bar
        _assert_component(frame_playback_bar())

    def test_multi_frame_row_returns_component(self):
        from archilume_app.components.frame_playback_bar import _multi_frame_row
        _assert_component(_multi_frame_row())

    def test_single_frame_row_returns_component(self):
        from archilume_app.components.frame_playback_bar import _single_frame_row
        _assert_component(_single_frame_row())


# =========================================================================
# project_tree.py
# =========================================================================


class TestProjectTree:
    def test_project_tree_returns_component(self):
        from archilume_app.components.project_tree import project_tree
        _assert_component(project_tree())

    def test_tree_header_returns_component(self):
        from archilume_app.components.project_tree import _tree_header
        _assert_component(_tree_header())


# =========================================================================
# modals.py
# =========================================================================


class TestModals:
    def test_all_public_modal_builders(self):
        import archilume_app.components.modals as m
        # Call every zero-arg public builder the module exposes.
        builders = [
            getattr(m, name) for name in dir(m)
            if not name.startswith("_")
            and callable(getattr(m, name))
            and name not in ("rx", "State", "EditorState")
        ]
        # At least one builder should exist and return a component.
        found_components = 0
        for fn in builders:
            try:
                result = fn()
            except TypeError:
                # Builder requires args we don't know — skip.
                continue
            except Exception:
                # Any other failure is a regression.
                raise
            if isinstance(result, rx.Component):
                found_components += 1
        assert found_components >= 1


# =========================================================================
# viewport.py
# =========================================================================


class TestViewport:
    def test_viewport_returns_component(self):
        from archilume_app.components.viewport import viewport
        _assert_component(viewport())


# =========================================================================
# right_panel.py
# =========================================================================


class TestRightPanel:
    def test_right_panel_returns_component(self):
        from archilume_app.components.right_panel import right_panel
        _assert_component(right_panel())


# =========================================================================
# left_panel_sections.py
# =========================================================================


class TestLeftPanelSections:
    def test_left_panel_tab_bar(self):
        import archilume_app.components.left_panel_sections as lp
        # Each zero-arg public builder must return a component.
        count = 0
        for name in dir(lp):
            if name.startswith("_"):
                continue
            fn = getattr(lp, name)
            if not callable(fn):
                continue
            try:
                r = fn()
            except TypeError:
                continue
            except Exception:
                raise
            if isinstance(r, rx.Component):
                count += 1
        assert count >= 1


# =========================================================================
# font_preview.py
# =========================================================================


class TestFontPreview:
    def test_font_preview_page_returns_component(self):
        from archilume_app.components.font_preview import font_preview_page
        _assert_component(font_preview_page())

    def test_font_card_returns_component(self):
        from archilume_app.components.font_preview import _font_card
        _assert_component(_font_card({
            "label": "Inter",
            "heading_font": "Inter, sans-serif",
            "body_font": "Inter, sans-serif",
            "current": False,
        }))
