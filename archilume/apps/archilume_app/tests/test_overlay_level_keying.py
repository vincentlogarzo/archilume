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
    overlay_page_idx: int = 0,
    overlay_page_count: int = 5,
) -> EditorState:
    state = object.__new__(EditorState)
    object.__setattr__(state, "dirty_vars", set())
    object.__setattr__(state, "_self_dirty_computed_vars", set())
    object.__setattr__(state, "base_state", state)
    object.__setattr__(state, "_auto_save", lambda: None)
    object.__setattr__(state, "_push_overlay_undo", lambda e: None)
    # Stub the page-dim refresh — pdf.js renders client-side, so the helper
    # would otherwise hit PyMuPDF on a non-existent path during these tests.
    object.__setattr__(state, "_refresh_overlay_page_dims", lambda: None)
    # Initialise _backend_vars so Reflex's __setattr__ can write backend vars
    # (vars with a leading underscore). Without this, assignments to e.g.
    # _overlay_undo_stack inside methods raise AttributeError.
    _bvars: dict = {}
    for k in EditorState.backend_vars:
        _bvars[k] = [] if k in ("_overlay_undo_stack", "_undo_stack", "_redo_stack") else \
                    {} if k in ("_overlay_session_start",) else \
                    None
    object.__setattr__(state, "_backend_vars", _bvars)

    state.view_groups = view_groups
    state.current_view_idx = current_view_idx
    state.current_frame_idx = current_frame_idx
    state.overlay_transforms = overlay_transforms or {}
    state.overlay_align_mode = overlay_align_mode
    state.overlay_page_idx = overlay_page_idx
    state.overlay_page_count = overlay_page_count
    state.overlay_visible = False
    state.overlay_pdf_path = ""

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


# ----------------------------------------------------------------- inherit-from-below


def test_inherit_copies_transform_from_level_below() -> None:
    state = _make_state(
        [
            _view_group("ffl_090000", ["s1"]),
            _view_group("ffl_093260", ["s1"]),
        ],
        current_view_idx=1,
        overlay_transforms={
            "ffl_090000": {"offset_x": 0.42, "offset_y": 0.17, "scale_x": 1.8, "scale_y": 1.8, "rotation_90": 1, "is_manual": True},
        },
    )
    state.inherit_from_level_below()
    t = state.overlay_transforms["ffl_093260"]
    assert t["offset_x"] == 0.42
    assert t["offset_y"] == 0.17
    assert t["scale_x"] == 1.8
    assert t["rotation_90"] == 1
    # is_manual is re-stamped by _set_current_overlay_transform, not inherited verbatim
    assert t["is_manual"] is True


def test_inherit_picks_nearest_level_below_not_lowest() -> None:
    state = _make_state(
        [
            _view_group("ffl_090000", ["s1"]),
            _view_group("ffl_093260", ["s1"]),
            _view_group("ffl_103180", ["s1"]),
        ],
        current_view_idx=2,  # on ffl_103180
        overlay_transforms={
            "ffl_090000": {"offset_x": 0.1, "is_manual": True},
            "ffl_093260": {"offset_x": 0.5, "is_manual": True},
        },
    )
    state.inherit_from_level_below()
    # Should copy from ffl_093260 (nearest below), not ffl_090000 (lowest).
    assert state.overlay_transforms["ffl_103180"]["offset_x"] == 0.5


def test_inherit_falls_back_to_centred_when_no_level_below() -> None:
    state = _make_state(
        [_view_group("ffl_090000", ["s1"])],
        current_view_idx=0,
    )
    state._set_current_overlay_transform({"offset_x": 0.9, "scale_x": 3.0})
    state.inherit_from_level_below()
    t = state.overlay_transforms["ffl_090000"]
    assert t["offset_x"] == 0.0
    assert t["offset_y"] == 0.0
    assert t["scale_x"] == 1.0


def test_inherit_falls_back_when_level_below_has_no_stored_transform() -> None:
    state = _make_state(
        [
            _view_group("ffl_090000", ["s1"]),
            _view_group("ffl_093260", ["s1"]),
        ],
        current_view_idx=1,
    )
    state._set_current_overlay_transform({"offset_x": 0.9, "scale_x": 3.0})
    state.inherit_from_level_below()
    t = state.overlay_transforms["ffl_093260"]
    assert t["offset_x"] == 0.0
    assert t["scale_x"] == 1.0


# ----------------------------------------------------------------- page-idx per-level


def test_inherit_advances_page_by_one_relative_to_level_below() -> None:
    """Symptom #1 fix: inherit_from_level_below must set page = below_page + 1,
    not copy the same page from below."""
    state = _make_state(
        [
            _view_group("ffl_090000", ["s1"]),
            _view_group("ffl_093260", ["s1"]),
        ],
        current_view_idx=1,
        overlay_transforms={
            "ffl_090000": {"offset_x": 0.42, "scale_x": 1.8, "page_idx": 2, "is_manual": True},
        },
        overlay_page_idx=0,  # current global page (should be overridden)
        overlay_page_count=5,
    )
    state.inherit_from_level_below()
    t = state.overlay_transforms["ffl_093260"]
    # Geometry inherited
    assert t["offset_x"] == 0.42
    assert t["scale_x"] == 1.8
    # Page advanced by 1: below was page 2, so this level should be page 3
    assert t["page_idx"] == 3
    assert state.overlay_page_idx == 3


def test_inherit_page_wraps_at_page_count() -> None:
    """Page advancement wraps modulo page_count (last page → page 0)."""
    state = _make_state(
        [
            _view_group("ffl_090000", ["s1"]),
            _view_group("ffl_093260", ["s1"]),
        ],
        current_view_idx=1,
        overlay_transforms={
            "ffl_090000": {"offset_x": 0.1, "scale_x": 1.0, "page_idx": 4, "is_manual": True},
        },
        overlay_page_count=5,
    )
    state.inherit_from_level_below()
    # 4 + 1 = 5 % 5 = 0
    assert state.overlay_transforms["ffl_093260"]["page_idx"] == 0


def test_cycle_page_persists_to_level_transform() -> None:
    """Symptom #4 fix: changing page on one level must not affect another level's
    stored page. After cycle_overlay_page, the new page must be in the level's
    overlay_transforms entry."""
    state = _make_state(
        [
            _view_group("ffl_090000", ["s1"]),
            _view_group("ffl_093260", ["s1"]),
        ],
        current_view_idx=0,
        overlay_transforms={
            "ffl_090000": {"offset_x": 0.0, "scale_x": 1.0, "page_idx": 0, "is_manual": True},
        },
        overlay_page_idx=0,
        overlay_page_count=5,
    )
    state.cycle_overlay_page()
    # The level's stored transform must now record page 1
    assert state.overlay_transforms["ffl_090000"]["page_idx"] == 1
    assert state.overlay_page_idx == 1
    # The other level's transform must be unaffected (not present)
    assert "ffl_093260" not in state.overlay_transforms


def test_set_transform_stores_current_page_idx() -> None:
    """_set_current_overlay_transform must record overlay_page_idx so the page
    survives level navigation and session save/restore."""
    state = _make_state(
        [_view_group("ffl_103180", ["s1"])],
        overlay_page_idx=3,
        overlay_page_count=5,
    )
    state._set_current_overlay_transform({"offset_x": 0.1, "scale_x": 1.2})
    stored = state.overlay_transforms["ffl_103180"]
    assert stored["page_idx"] == 3


def test_set_transform_does_not_override_explicit_page_idx() -> None:
    """If the caller already supplies page_idx (e.g. inherit_from_level_below),
    the stored value wins over the global overlay_page_idx."""
    state = _make_state(
        [_view_group("ffl_103180", ["s1"])],
        overlay_page_idx=0,  # global is 0
        overlay_page_count=5,
    )
    state._set_current_overlay_transform({"offset_x": 0.1, "page_idx": 4})
    assert state.overlay_transforms["ffl_103180"]["page_idx"] == 4


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


# ----------------------------------------------------------------- undo page sync


def test_undo_page_change_syncs_page_idx_into_level_transform() -> None:
    """After undoing a page cycle, overlay_transforms[level_key]['page_idx'] must
    match the restored overlay_page_idx, so navigating away and back shows the
    correct (undone) page rather than the pre-undo (newer) page."""
    state = _make_state(
        [_view_group("ffl_103180", ["s1"])],
        overlay_page_idx=1,   # global page after cycle
        overlay_page_count=5,
        overlay_transforms={
            "ffl_103180": {"offset_x": 0.0, "scale_x": 1.0, "page_idx": 1, "is_manual": True},
        },
    )
    # _overlay_undo_stack is a Reflex backend var — assign via normal setattr
    # (not object.__setattr__) so the _backend_vars dict is updated correctly.
    undo_entry = {
        "action": "overlay_props",
        "desc": "Change overlay page",
        "before": {"page_idx": 0, "alpha": 0.6},
        "after": {"page_idx": 1, "alpha": 0.6},
    }
    state._overlay_undo_stack = [undo_entry]
    state._overlay_session_start = {}
    state.overlay_alpha = 0.6
    state._undo_overlay()
    # Global page_idx must be restored to the before value
    assert state.overlay_page_idx == 0
    # Per-level transform must also be updated so navigation restores the right page
    assert state.overlay_transforms["ffl_103180"]["page_idx"] == 0


# -------------------------------------------------------- goto_frame page restore


def test_restore_overlay_page_infers_when_transform_lacks_page_idx() -> None:
    """Legacy sessions stored overlay_transforms entries without page_idx. When
    the user navigates to such a level, the first-branch restore must NOT swallow
    control — it must fall through to the auto-inherit path so the global
    overlay_page_idx does not leak from the previously viewed level."""
    state = _make_state(
        [
            _view_group("ffl_090000", ["s1"]),
            _view_group("ffl_103180", ["s1"]),
        ],
        current_view_idx=1,
        overlay_page_idx=2,  # leaked from level below
        overlay_page_count=5,
        overlay_transforms={
            "ffl_090000": {"offset_x": 0.0, "scale_x": 1.0, "page_idx": 2, "is_manual": True},
            # Legacy transform: spatial only, no page_idx field.
            "ffl_103180": {"offset_x": 0.2, "scale_x": 1.1, "is_manual": True},
        },
    )
    state.overlay_pdf_path = "/tmp/plans.pdf"
    state._restore_overlay_page_for_current_level()
    # Must auto-inherit (2 + 1 = 3), not leak the previous level's 2.
    assert state.overlay_page_idx == 3


def test_restore_overlay_page_uses_stored_page_idx_when_present() -> None:
    """Common case: level transform has stored page_idx. Restore it verbatim,
    overriding whatever the global held from prior navigation."""
    state = _make_state(
        [
            _view_group("ffl_090000", ["s1"]),
            _view_group("ffl_103180", ["s1"]),
        ],
        current_view_idx=1,
        overlay_page_idx=4,  # leaked from elsewhere
        overlay_page_count=5,
        overlay_transforms={
            "ffl_090000": {"offset_x": 0.0, "scale_x": 1.0, "page_idx": 0, "is_manual": True},
            "ffl_103180": {"offset_x": 0.2, "scale_x": 1.1, "page_idx": 1, "is_manual": True},
        },
    )
    state.overlay_pdf_path = "/tmp/plans.pdf"
    state._restore_overlay_page_for_current_level()
    assert state.overlay_page_idx == 1


def test_restore_overlay_page_on_bottom_level_with_stale_transform_defaults_to_zero() -> None:
    """Navigating DOWN to the bottom level — which has a legacy transform without
    page_idx and no level below — must not inherit a leaked upper-level page.
    Infers to 0 (no below, so fall-back default)."""
    state = _make_state(
        [
            _view_group("ffl_090000", ["s1"]),
            _view_group("ffl_103180", ["s1"]),
        ],
        current_view_idx=0,
        overlay_page_idx=3,  # leaked from upper level
        overlay_page_count=5,
        overlay_transforms={
            "ffl_090000": {"offset_x": 0.0, "scale_x": 1.0, "is_manual": True},
            "ffl_103180": {"offset_x": 0.2, "scale_x": 1.1, "page_idx": 3, "is_manual": True},
        },
    )
    state.overlay_pdf_path = "/tmp/plans.pdf"
    state._restore_overlay_page_for_current_level()
    # Bottom level, no below — must default to 0, not leak 3.
    assert state.overlay_page_idx == 0


def test_restore_overlay_page_noop_when_pdf_not_attached() -> None:
    """With no PDF attached, overlay_page_idx should not be touched — avoids
    spurious state diffs when the overlay feature isn't in use."""
    state = _make_state(
        [_view_group("ffl_090000", ["s1"])],
        current_view_idx=0,
        overlay_page_idx=2,
        overlay_page_count=0,  # no PDF = no pages
    )
    state.overlay_pdf_path = ""
    state._restore_overlay_page_for_current_level()
    assert state.overlay_page_idx == 2
