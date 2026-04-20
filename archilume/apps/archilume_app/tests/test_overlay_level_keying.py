"""Tests for per-level PDF underlay transform storage.

Before v5, ``overlay_transforms`` was keyed by HDR filename stem — in sunlight
mode, one slot per timestep frame (e.g. 125 slots per level). v5 keys by level
(``view_groups[*].view_name``), so every frame of a level shares one transform.

Also covers the v4→v5 migration that collapses per-stem keys to per-level keys,
preferring a frame marked ``is_manual=True`` when multiple frames of a level
hold a stored transform.
"""

from __future__ import annotations

import pytest

from archilume_app.state.editor_state import EditorState, _stem_to_view_map


def _view_group(view_name: str, stems: list[str]) -> dict:
    return {
        "view_name": view_name,
        "view_prefix": f"octree_{view_name}",
        "frames": [
            {
                "hdr_path": f"/tmp/{view_name}_{s}.hdr",
                "png_path": f"/tmp/{view_name}_{s}.png",
                "sky_name": s,
                "hdr_stem": f"{view_name}_{s}",
                "frame_label": s,
            }
            for s in stems
        ],
    }


def _make_state(
    view_groups: list[dict],
    current_view_idx: int = 0,
    current_frame_idx: int = 0,
    overlay_transforms: dict | None = None,
    overlay_align_mode: bool = False,
) -> EditorState:
    state = object.__new__(EditorState)
    object.__setattr__(state, "dirty_vars", set())
    object.__setattr__(state, "_self_dirty_computed_vars", set())
    object.__setattr__(state, "base_state", state)
    object.__setattr__(state, "_auto_save", lambda: None)
    object.__setattr__(state, "_push_overlay_undo", lambda e: None)

    state.view_groups = view_groups
    state.current_view_idx = current_view_idx
    state.current_frame_idx = current_frame_idx
    state.overlay_transforms = overlay_transforms or {}
    state.overlay_align_mode = overlay_align_mode

    # hdr_files mirrors the frames flattened in view-group order so
    # _current_level_key's daylight fallback path never triggers in these tests.
    state.hdr_files = [
        {"name": f["hdr_stem"], "hdr_path": f["hdr_path"], "tiff_paths": [], "suffix": "", "legend_map": {}}
        for vg in view_groups for f in vg["frames"]
    ]
    state.current_hdr_idx = 0

    # Fields referenced by _set_current_overlay_transform logging.
    state.viewport_width = 1000
    state.image_width = 800
    state.image_height = 600
    state.overlay_img_width = 400
    state.overlay_img_height = 300
    return state


# ----------------------------------------------------------------- helper


def test_stem_to_view_map_flattens_all_frames() -> None:
    groups = [
        _view_group("ffl_090000", ["s1", "s2"]),
        _view_group("ffl_103180", ["s1", "s2", "s3"]),
    ]
    assert _stem_to_view_map(groups) == {
        "ffl_090000_s1": "ffl_090000",
        "ffl_090000_s2": "ffl_090000",
        "ffl_103180_s1": "ffl_103180",
        "ffl_103180_s2": "ffl_103180",
        "ffl_103180_s3": "ffl_103180",
    }


def test_stem_to_view_map_empty_for_daylight() -> None:
    assert _stem_to_view_map([]) == {}


# ----------------------------------------------------------------- level key


def test_current_level_key_returns_view_name_in_sunlight() -> None:
    state = _make_state([_view_group("ffl_090000", ["s1", "s2", "s3"])])
    state.current_frame_idx = 2
    assert state._current_level_key() == "ffl_090000"


def test_current_level_key_falls_back_to_hdr_name_in_daylight() -> None:
    state = _make_state([])
    state.hdr_files = [{"name": "room_A", "hdr_path": "", "tiff_paths": [], "suffix": "", "legend_map": {}}]
    state.current_hdr_idx = 0
    assert state._current_level_key() == "room_A"


# ----------------------------------------------------------------- set/get


def test_set_transform_stores_under_level_key() -> None:
    state = _make_state([_view_group("ffl_103180", ["s1", "s2", "s3"])])
    state._set_current_overlay_transform({"offset_x": 0.25, "offset_y": -0.1, "scale_x": 1.2, "scale_y": 1.2})
    assert list(state.overlay_transforms.keys()) == ["ffl_103180"]
    stored = state.overlay_transforms["ffl_103180"]
    assert stored["offset_x"] == 0.25
    assert stored["is_manual"] is True


def test_get_transform_shared_across_frames_of_same_level() -> None:
    state = _make_state([_view_group("ffl_103180", ["s1", "s2", "s3"])])
    state.current_frame_idx = 0
    state._set_current_overlay_transform({"offset_x": 0.42})
    # Navigate to a different frame of the same level — transform must follow.
    state.current_frame_idx = 2
    assert state._get_current_overlay_transform()["offset_x"] == 0.42
    # Still exactly one key in the dict (no per-frame fan-out).
    assert len(state.overlay_transforms) == 1


def test_get_transform_returns_centred_default_for_unset_level() -> None:
    state = _make_state([
        _view_group("ffl_090000", ["s1"]),
        _view_group("ffl_103180", ["s1"]),
    ])
    # Set on level 0, check level 1 gets centred default (no inheritance).
    state.current_view_idx = 0
    state._set_current_overlay_transform({"offset_x": 0.9, "scale_x": 2.0})
    state.current_view_idx = 1
    t = state._get_current_overlay_transform()
    assert t == {"offset_x": 0.0, "offset_y": 0.0, "scale_x": 1.0, "scale_y": 1.0, "rotation_90": 0}


# ----------------------------------------------------------------- migration


def test_migrate_v4_to_v5_collapses_stems_to_level() -> None:
    state = _make_state(
        [_view_group("ffl_103180", ["SS_0621_1500", "SS_0621_1445", "SS_0621_1430"])],
        overlay_transforms={
            "ffl_103180_SS_0621_1500": {"offset_x": 0.1, "is_manual": True},
            "ffl_103180_SS_0621_1445": {"offset_x": 0.2, "is_manual": False},
            "ffl_103180_SS_0621_1430": {"offset_x": 0.3, "is_manual": False},
        },
    )
    state._migrate_overlay_keys_to_level()
    assert list(state.overlay_transforms.keys()) == ["ffl_103180"]
    # is_manual wins over the earlier non-manual siblings.
    assert state.overlay_transforms["ffl_103180"]["offset_x"] == 0.1


def test_migrate_prefers_any_when_no_manual_flag() -> None:
    state = _make_state(
        [_view_group("ffl_090000", ["SS_1", "SS_2"])],
        overlay_transforms={
            "ffl_090000_SS_1": {"offset_x": 0.5},
            "ffl_090000_SS_2": {"offset_x": 0.7},
        },
    )
    state._migrate_overlay_keys_to_level()
    assert list(state.overlay_transforms.keys()) == ["ffl_090000"]
    # Picks first encountered when none are manual.
    assert state.overlay_transforms["ffl_090000"]["offset_x"] == 0.5


def test_migrate_is_idempotent_for_already_level_keyed() -> None:
    state = _make_state(
        [_view_group("ffl_103180", ["SS_1", "SS_2"])],
        overlay_transforms={"ffl_103180": {"offset_x": 0.33, "is_manual": True}},
    )
    state._migrate_overlay_keys_to_level()
    assert state.overlay_transforms == {"ffl_103180": {"offset_x": 0.33, "is_manual": True}}


def test_migrate_preserves_orphaned_stems() -> None:
    """Stems not found in any current view (e.g. deleted frame) are preserved
    rather than silently dropped, so re-adding the frame later restores the
    transform."""
    state = _make_state(
        [_view_group("ffl_103180", ["SS_1"])],
        overlay_transforms={
            "ffl_103180_SS_1": {"offset_x": 0.1, "is_manual": True},
            "ffl_DELETED_SS_9": {"offset_x": 0.9, "is_manual": True},
        },
    )
    state._migrate_overlay_keys_to_level()
    assert state.overlay_transforms["ffl_103180"]["offset_x"] == 0.1
    assert state.overlay_transforms["ffl_DELETED_SS_9"]["offset_x"] == 0.9


def test_migrate_noop_when_view_groups_empty() -> None:
    """Daylight projects (view_groups empty) already have hdr_name ≈ view_name,
    so migration leaves them alone."""
    state = _make_state([], overlay_transforms={"room_A": {"offset_x": 0.2, "is_manual": True}})
    state._migrate_overlay_keys_to_level()
    assert state.overlay_transforms == {"room_A": {"offset_x": 0.2, "is_manual": True}}


# ----------------------------------------------------------------- reset


def test_reset_level_alignment_centres_current_level() -> None:
    state = _make_state([_view_group("ffl_103180", ["s1", "s2"])])
    state._set_current_overlay_transform({"offset_x": 0.9, "scale_x": 3.0})
    assert state.overlay_transforms["ffl_103180"]["offset_x"] == 0.9
    state.reset_level_alignment()
    t = state.overlay_transforms["ffl_103180"]
    assert t["offset_x"] == 0.0
    assert t["offset_y"] == 0.0
    assert t["scale_x"] == 1.0


# ----------------------------------------------------------------- undo payload


def test_undo_payload_carries_level_key_not_hdr_name() -> None:
    captured: list[dict] = []
    state = _make_state(
        [_view_group("ffl_103180", ["s1", "s2"])],
        overlay_align_mode=True,
    )
    object.__setattr__(state, "_push_overlay_undo", captured.append)
    state._set_current_overlay_transform({"offset_x": 0.1})
    assert len(captured) == 1
    entry = captured[0]
    assert entry["action"] == "overlay_transform"
    assert entry["before"]["level_key"] == "ffl_103180"
    assert entry["after"]["level_key"] == "ffl_103180"
    assert "hdr_name" not in entry["before"]
    assert "hdr_name" not in entry["after"]
