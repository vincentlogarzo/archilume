"""Isolated unit tests for ``EditorState`` computed vars and simple setters.

Uses the ``make_editor_state`` fixture from the repo-root ``conftest.py`` to
bypass Reflex's ``__init__``. Focuses on the pure-logic slice of state
methods — no file IO, no rasterization, no PDF dialogs.
"""

from __future__ import annotations

import pytest


# =========================================================================
# current_* computed vars
# =========================================================================


class TestCurrentHdrAndFrame:
    def test_current_hdr_name_empty_when_no_hdrs(self, make_editor_state):
        s = make_editor_state(hdr_files=[], current_hdr_idx=0)
        assert s.current_hdr_name == "No images"

    def test_current_hdr_name_reads_current_entry(self, make_editor_state):
        s = make_editor_state(
            hdr_files=[{"name": "a.hdr"}, {"name": "b.hdr"}],
            current_hdr_idx=1,
        )
        assert s.current_hdr_name == "b.hdr"

    def test_current_hdr_count_formats_position(self, make_editor_state):
        s = make_editor_state(
            hdr_files=[{"name": "a"}, {"name": "b"}, {"name": "c"}],
            current_hdr_idx=1,
        )
        assert s.current_hdr_count == "2 / 3"

    def test_current_hdr_count_blank_when_empty(self, make_editor_state):
        assert make_editor_state(hdr_files=[]).current_hdr_count == ""


# =========================================================================
# Room-input helper vars
# =========================================================================


class TestRoomInputVars:
    def test_resolved_room_name_empty_when_no_input(self, make_editor_state):
        s = make_editor_state(room_name_input="", selected_parent="")
        assert s.resolved_room_name == ""

    def test_resolved_room_name_with_parent(self, make_editor_state):
        s = make_editor_state(room_name_input="T1", selected_parent="3BED")
        assert s.resolved_room_name == "→ 3BED_T1"

    def test_resolved_room_name_without_parent(self, make_editor_state):
        s = make_editor_state(room_name_input="BED1", selected_parent="")
        assert s.resolved_room_name == "→ BED1"


# =========================================================================
# Multi-selection computed vars
# =========================================================================


class TestMultiSelection:
    def test_has_multi_selection_requires_more_than_one(self, make_editor_state):
        assert make_editor_state(multi_selected_idxs=[]).has_multi_selection is False
        assert make_editor_state(multi_selected_idxs=[1]).has_multi_selection is False
        assert make_editor_state(
            multi_selected_idxs=[1, 2],
        ).has_multi_selection is True

    def test_multi_selection_count(self, make_editor_state):
        assert make_editor_state(multi_selected_idxs=[1, 2, 3]).multi_selection_count == 3

    def test_all_rooms_selected_false_when_no_hdrs(self, make_editor_state):
        assert make_editor_state(
            hdr_files=[], rooms=[], multi_selected_idxs=[],
        ).all_rooms_selected is False

    def test_all_rooms_selected_true_when_every_room_selected(self, make_editor_state):
        s = make_editor_state(
            hdr_files=[{"name": "a"}], current_hdr_idx=0,
            rooms=[{"hdr_file": "a"}, {"hdr_file": "a"}],
            multi_selected_idxs=[0, 1],
        )
        assert s.all_rooms_selected is True


# =========================================================================
# View/frame computed vars (sunlight mode)
# =========================================================================


def _view_group(view_name: str, frames: list[str]) -> dict:
    return {
        "view_name": view_name,
        "frames": [{"frame_label": f} for f in frames],
    }


class TestViewFrameVars:
    def test_frame_count_zero_without_groups(self, make_editor_state):
        assert make_editor_state(
            view_groups=[], current_view_idx=0,
        ).current_view_frame_count == 0

    def test_frame_count_matches_group(self, make_editor_state):
        groups = [_view_group("v1", ["a", "b", "c"])]
        s = make_editor_state(view_groups=groups, current_view_idx=0)
        assert s.current_view_frame_count == 3

    def test_current_frame_label_blank_without_groups(self, make_editor_state):
        assert make_editor_state(view_groups=[]).current_frame_label == ""

    def test_current_frame_label_returns_indexed_label(self, make_editor_state):
        groups = [_view_group("v1", ["F0", "F1"])]
        s = make_editor_state(
            view_groups=groups, current_view_idx=0, current_frame_idx=1,
        )
        assert s.current_frame_label == "F1"

    def test_current_frame_label_clamps_out_of_range(self, make_editor_state):
        groups = [_view_group("v1", ["F0", "F1"])]
        s = make_editor_state(
            view_groups=groups, current_view_idx=0, current_frame_idx=99,
        )
        assert s.current_frame_label == "F1"

    def test_current_view_name_empty_when_no_groups(self, make_editor_state):
        assert make_editor_state(view_groups=[]).current_view_name == ""

    def test_is_sunlight_mode_requires_mode_and_groups(self, make_editor_state):
        s = make_editor_state(
            project_mode="sunlight", view_groups=[_view_group("v", ["a"])],
        )
        assert s.is_sunlight_mode is True
        assert make_editor_state(
            project_mode="aoi", view_groups=[_view_group("v", ["a"])],
        ).is_sunlight_mode is False
        assert make_editor_state(
            project_mode="sunlight", view_groups=[],
        ).is_sunlight_mode is False


# =========================================================================
# Viewport / SVG / zoom computed vars
# =========================================================================


class TestViewportAndZoom:
    def test_zoom_pct_formats_percentage(self, make_editor_state):
        assert make_editor_state(zoom_level=1.5).zoom_pct == "150%"
        assert make_editor_state(zoom_level=0.8).zoom_pct == "80%"

    def test_svg_viewbox_uses_image_size(self, make_editor_state):
        s = make_editor_state(image_width=640, image_height=480)
        assert s.svg_viewbox == "0 0 640 480"

    def test_svg_viewbox_fallback(self, make_editor_state):
        s = make_editor_state(image_width=0, image_height=0)
        assert s.svg_viewbox == "0 0 1000 800"


# =========================================================================
# Grid / spacing vars
# =========================================================================


class TestGridSpacing:
    def test_grid_spacing_zero_without_hdr(self, make_editor_state):
        s = make_editor_state(
            hdr_files=[], current_hdr_idx=0,
            hdr_view_params={}, image_width=100, grid_spacing_mm=100,
        )
        assert s.grid_spacing_px == 0.0

    def test_grid_spacing_computes_from_vp_params(self, make_editor_state):
        # vp = [vpx, vpy, vh=10m, vv=10m, iw=100, ih=100] → 0.1 m/px.
        # 100 mm spacing = 0.1 m → 1 px.
        s = make_editor_state(
            hdr_files=[{"name": "a"}], current_hdr_idx=0,
            hdr_view_params={"a": [0, 0, 10, 10, 100, 100]},
            image_width=100, grid_spacing_mm=100,
        )
        assert s.grid_spacing_px == pytest.approx(1.0)

    def test_grid_pattern_size_falls_back_when_spacing_zero(self, make_editor_state):
        s = make_editor_state(
            hdr_files=[], hdr_view_params={}, image_width=0,
            grid_spacing_mm=100, current_hdr_idx=0,
        )
        assert s.grid_pattern_size == "10"

    def test_grid_offset_x_default_when_no_vp(self, make_editor_state):
        s = make_editor_state(
            hdr_files=[{"name": "a"}], current_hdr_idx=0,
            hdr_view_params={},
            image_width=100, grid_spacing_mm=100,
        )
        assert s.grid_offset_x == "0"

    def test_grid_offset_y_default_when_no_vp(self, make_editor_state):
        s = make_editor_state(
            hdr_files=[{"name": "a"}], current_hdr_idx=0,
            hdr_view_params={},
            image_height=100, grid_spacing_mm=100,
        )
        assert s.grid_offset_y == "0"


# =========================================================================
# Annotation / DF-stamp font sizes
# =========================================================================


class TestAnnotationFontSizes:
    def test_label_font_size_scales_inversely_with_zoom(self, make_editor_state):
        lo = make_editor_state(annotation_scale=1.0, zoom_level=1.0).label_font_size
        hi_zoom = make_editor_state(annotation_scale=1.0, zoom_level=4.0).label_font_size
        assert float(hi_zoom) < float(lo)

    def test_label_font_size_clamped(self, make_editor_state):
        # Very large scale + tiny zoom → clamp top (30).
        s = make_editor_state(annotation_scale=100.0, zoom_level=0.01)
        assert float(s.label_font_size) == 30.0
        # Very small scale + huge zoom → clamp bottom (2.0).
        s2 = make_editor_state(annotation_scale=0.01, zoom_level=100.0)
        assert float(s2.label_font_size) == 2.0

    def test_df_stamp_font_size_clamped(self, make_editor_state):
        s = make_editor_state(annotation_scale=100.0, zoom_level=0.01)
        assert float(s.df_stamp_font_size) == 10.0
        s2 = make_editor_state(annotation_scale=0.01, zoom_level=100.0)
        assert float(s2.df_stamp_font_size) == 1.0

    def test_df_stamp_bg_width_clamped(self, make_editor_state):
        s = make_editor_state(annotation_scale=100.0, zoom_level=0.01)
        assert float(s.df_stamp_bg_width) == 110.0
        s2 = make_editor_state(annotation_scale=0.01, zoom_level=100.0)
        assert float(s2.df_stamp_bg_width) == 8.0

    def test_df_stamp_bg_height_is_twice_font(self, make_editor_state):
        s = make_editor_state(annotation_scale=1.0, zoom_level=1.0)
        fs = s._df_fs_val()
        assert float(s.df_stamp_bg_height) == pytest.approx(round(fs * 2.0, 1))

    def test_df_stamp_bg_half_f_is_font(self, make_editor_state):
        s = make_editor_state(annotation_scale=1.0, zoom_level=1.0)
        fs = s._df_fs_val()
        assert s.df_stamp_bg_half_f == pytest.approx(round(fs, 2))


# =========================================================================
# Simple event-handler setters
# =========================================================================


class TestSimpleSetters:
    def test_set_room_name(self, make_editor_state):
        s = make_editor_state(room_name_input="")
        s.set_room_name("ROOM1")
        assert s.room_name_input == "ROOM1"

    def test_set_viewport_size(self, make_editor_state):
        s = make_editor_state(
            viewport_width=0, viewport_height=0,
            _legacy_overlay_pending=False,
        )
        s.set_viewport_size({"w": 1024, "h": 768})
        assert s.viewport_width == 1024
        assert s.viewport_height == 768

    def test_set_viewport_size_handles_missing_keys(self, make_editor_state):
        s = make_editor_state(
            viewport_width=0, viewport_height=0,
            _legacy_overlay_pending=False,
        )
        s.set_viewport_size({})
        assert s.viewport_width == 0

    def test_set_active_tab(self, make_editor_state):
        s = make_editor_state(active_tab="")
        s.set_active_tab("Viewer")
        assert s.active_tab == "Viewer"

    def test_toggle_grid(self, make_editor_state):
        s = make_editor_state(grid_visible=False)
        s.toggle_grid()
        assert s.grid_visible is True
        s.toggle_grid()
        assert s.grid_visible is False

    def test_toggle_ortho(self, make_editor_state):
        s = make_editor_state(
            ortho_mode=False, status_message="",
        )
        s.toggle_ortho()
        assert s.ortho_mode is True
        assert "ON" in s.status_message

    def test_toggle_legend_pin(self, make_editor_state):
        s = make_editor_state(legend_pinned=False)
        s.toggle_legend_pin()
        assert s.legend_pinned is True

    def test_set_legend_hovered(self, make_editor_state):
        s = make_editor_state(legend_hovered=False)
        s.set_legend_hovered(True)
        assert s.legend_hovered is True

    def test_set_grid_spacing_valid_int(self, make_editor_state):
        s = make_editor_state(grid_spacing_mm=100)
        s.set_grid_spacing("250")
        assert s.grid_spacing_mm == 250

    def test_set_grid_spacing_clamps_small_values(self, make_editor_state):
        s = make_editor_state(grid_spacing_mm=100)
        s.set_grid_spacing("1")
        assert s.grid_spacing_mm == 5  # minimum floor

    def test_set_grid_spacing_invalid_ignored(self, make_editor_state):
        s = make_editor_state(grid_spacing_mm=100)
        s.set_grid_spacing("not a number")
        assert s.grid_spacing_mm == 100


# =========================================================================
# Frame playback setters
# =========================================================================


class TestFramePlayback:
    def test_set_frame_fps_clamps_to_range(self, make_editor_state):
        s = make_editor_state(frame_playback_fps=5)
        s.set_frame_fps("60")
        assert s.frame_playback_fps == 30  # clamped to 30
        s.set_frame_fps("0")
        assert s.frame_playback_fps == 1  # clamped to 1

    def test_set_frame_fps_invalid_noop(self, make_editor_state):
        s = make_editor_state(frame_playback_fps=10)
        s.set_frame_fps("bad")
        assert s.frame_playback_fps == 10

    def test_advance_frame_skips_when_not_autoplaying(self, make_editor_state):
        groups = [_view_group("v1", ["a", "b"])]
        s = make_editor_state(
            view_groups=groups, current_view_idx=0,
            current_frame_idx=0, frame_autoplay=False,
        )
        s.advance_frame()
        assert s.current_frame_idx == 0

    def test_toggle_frame_autoplay_requires_multiple_frames(self, make_editor_state):
        single = [_view_group("v1", ["only"])]
        s = make_editor_state(
            view_groups=single, current_view_idx=0, frame_autoplay=True,
        )
        s.toggle_frame_autoplay()
        assert s.frame_autoplay is False

    def test_toggle_frame_autoplay_noop_without_groups(self, make_editor_state):
        s = make_editor_state(view_groups=[], frame_autoplay=True)
        s.toggle_frame_autoplay()
        assert s.frame_autoplay is True  # unchanged


# =========================================================================
# Multi-selection event handlers
# =========================================================================


class TestSelectAllRooms:
    def test_noop_when_no_hdrs_in_aoi_mode(self, make_editor_state):
        s = make_editor_state(
            project_mode="aoi", hdr_files=[], view_groups=[],
            rooms=[], multi_selected_idxs=[],
        )
        s.select_all_rooms()
        assert s.multi_selected_idxs == []

    def test_toggles_select_all_in_aoi_mode(self, make_editor_state):
        s = make_editor_state(
            project_mode="aoi",
            hdr_files=[{"name": "a"}], current_hdr_idx=0,
            view_groups=[],
            rooms=[{"hdr_file": "a"}, {"hdr_file": "a"}],
            multi_selected_idxs=[], selected_room_idx=-1,
        )
        s.select_all_rooms()
        assert sorted(s.multi_selected_idxs) == [0, 1]
        s.select_all_rooms()  # second call deselects
        assert s.multi_selected_idxs == []
