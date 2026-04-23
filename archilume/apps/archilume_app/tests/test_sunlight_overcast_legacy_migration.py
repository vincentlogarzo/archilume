"""Tests for ``_migrate_sunlight_room_keys`` recovery of legacy overcast keys.

Earlier iterations of ``scan_sunlight_view_groups`` enumerated the overcast
HDR as its own view group, so rooms drawn on the overcast baseline persisted
with ``hdr_file`` values like ``093260__TenK_cie_overcast`` (the old trimmed
view_name). After commits 434637f + 81e1ce3 demoted overcast to an underlay,
migration's stem→view map no longer covers those legacy strings and rooms
stop rendering because ``enriched_rooms`` filters them out.

The migration now has a three-tier lookup:
  1. Key is already a current view_name → no-op.
  2. Key is a frame or underlay stem → map via ``_stem_to_view_map``.
  3. Key contains the same FFL digit run as exactly one current view_name
     (legacy fallback) → map to that view_name.
"""

from __future__ import annotations

from archilume_app.state.editor_state import EditorState


def _view_group(
    view_name: str,
    frame_stems: list[str],
    underlay_hdr_stem: str = "",
) -> dict:
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
            for s in frame_stems
        ],
        "underlay_png_path": f"/tmp/{underlay_hdr_stem}.png" if underlay_hdr_stem else "",
        "underlay_hdr_stem": underlay_hdr_stem,
    }


def _bare_sunlight_state(view_groups: list, rooms: list) -> EditorState:
    """Minimal state for testing migration (no enriched_rooms call)."""
    state = object.__new__(EditorState)
    object.__setattr__(state, "dirty_vars", set())
    object.__setattr__(state, "_self_dirty_computed_vars", set())
    object.__setattr__(state, "base_state", state)
    state.project_mode = "sunlight"
    state.view_groups = view_groups
    state.rooms = rooms
    return state


def test_migration_recovers_legacy_overcast_view_name() -> None:
    """Room saved with legacy overcast-as-view key should migrate to the
    current view_name by FFL-digit fallback."""
    vg = _view_group(
        "ffl_093260",
        ["SS_0621_0900"],
        underlay_hdr_stem="octree_ffl_093260__TenK_cie_overcast",
    )
    room = {
        "name": "U101_2_BED",
        "hdr_file": "093260__TenK_cie_overcast",  # legacy trimmed form
        "world_vertices": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
        "vertices": [],
        "visible": True,
        "parent": "",
    }
    state = _bare_sunlight_state([vg], [room])

    state._migrate_sunlight_room_keys()

    assert state.rooms[0]["hdr_file"] == "ffl_093260"


def test_migration_maps_underlay_hdr_stem_via_stem_map() -> None:
    """Room saved with the full underlay HDR stem migrates to the view_name
    via the extended ``_stem_to_view_map`` (no FFL fallback needed)."""
    underlay_stem = "octree_ffl_093260__TenK_cie_overcast"
    vg = _view_group("ffl_093260", ["SS_0621_0900"], underlay_hdr_stem=underlay_stem)
    room = {
        "name": "U101",
        "hdr_file": underlay_stem,
        "world_vertices": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
        "vertices": [],
        "visible": True,
    }
    state = _bare_sunlight_state([vg], [room])

    state._migrate_sunlight_room_keys()

    assert state.rooms[0]["hdr_file"] == "ffl_093260"


def test_migration_idempotent_for_current_view_names() -> None:
    """Rooms already keyed to a current view_name are left untouched."""
    vg = _view_group("ffl_093260", ["SS_0621_0900"])
    room = {
        "name": "R1",
        "hdr_file": "ffl_093260",
        "world_vertices": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
        "vertices": [],
        "visible": True,
    }
    state = _bare_sunlight_state([vg], [room])

    state._migrate_sunlight_room_keys()

    assert state.rooms[0]["hdr_file"] == "ffl_093260"


def test_migration_noop_when_view_groups_empty() -> None:
    """Daylight mode (empty view_groups) → migration returns early, rooms untouched."""
    room = {
        "name": "R1",
        "hdr_file": "room_A",  # daylight per-HDR key
        "world_vertices": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
        "vertices": [],
        "visible": True,
    }
    state = _bare_sunlight_state([], [room])

    state._migrate_sunlight_room_keys()

    assert state.rooms[0]["hdr_file"] == "room_A"


def test_migration_skips_ambiguous_ffl_token() -> None:
    """Legacy key whose FFL digit run matches multiple view_names is left
    untouched (silent corruption guard)."""
    vg_a = _view_group("ffl_090000_a", ["SS_0900"])
    vg_b = _view_group("ffl_090000_b", ["SS_0900"])
    room = {
        "name": "R1",
        "hdr_file": "090000__TenK_cie_overcast",
        "world_vertices": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
        "vertices": [],
        "visible": True,
    }
    state = _bare_sunlight_state([vg_a, vg_b], [room])

    state._migrate_sunlight_room_keys()

    assert state.rooms[0]["hdr_file"] == "090000__TenK_cie_overcast"


def _enriched_rooms_state(
    view_name: str, stems: list[str], rooms: list, underlay_stem: str = ""
) -> EditorState:
    """Fully-wired sunlight state capable of evaluating ``enriched_rooms``.

    Pattern lifted from ``test_enriched_rooms_level_keying.py``.
    """
    state = object.__new__(EditorState)
    object.__setattr__(state, "dirty_vars", set())
    object.__setattr__(state, "_self_dirty_computed_vars", set())
    object.__setattr__(state, "base_state", state)

    vg = _view_group(view_name, stems, underlay_hdr_stem=underlay_stem)
    state.project_mode = "sunlight"
    state.view_groups = [vg]
    state.current_view_idx = 0
    state.current_frame_idx = 0
    state.hdr_files = [
        {
            "name": f["hdr_stem"],
            "hdr_path": f["hdr_path"],
            "tiff_paths": [],
            "suffix": "",
            "legend_map": {},
        }
        for f in vg["frames"]
    ]
    state.current_hdr_idx = 0
    state.image_width = 100
    state.image_height = 100
    state.hdr_view_params = {
        f["hdr_stem"]: [0.0, 0.0, 10.0, 10.0, 100, 100] for f in vg["frames"]
    }
    state.room_df_results = {}
    state.annotation_scale = 1.0
    state.selected_room_idx = -1
    state.multi_selected_idxs = []
    state.rooms = rooms
    return state


def test_enriched_rooms_renders_after_legacy_key_migration() -> None:
    """End-to-end: room with legacy overcast hdr_file becomes visible in
    ``enriched_rooms`` once migration repairs the key. This is the regression
    test that would have caught the cowles bug."""
    legacy_room = {
        "name": "U101_2_BED",
        "hdr_file": "093260__TenK_cie_overcast",  # legacy value
        "world_vertices": [[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0]],
        "vertices": [],
        "visible": True,
        "parent": "",
        "room_type": "NONE",
    }
    state = _enriched_rooms_state(
        "ffl_093260",
        ["SS_0621_0900"],
        [legacy_room],
        underlay_stem="octree_ffl_093260__TenK_cie_overcast",
    )

    assert state.enriched_rooms == [], (
        "precondition: legacy-keyed room is filtered out before migration"
    )

    state._migrate_sunlight_room_keys()

    enriched = state.enriched_rooms
    assert len(enriched) == 1, "post-migration: room should render on viewport"
    assert enriched[0]["name"] == "U101_2_BED"
