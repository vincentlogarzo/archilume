"""Tests that ``enriched_rooms`` selects rooms by the per-level key in
sunlight mode, so one room set applies to every timestep frame of its level.

v5 moved room ``hdr_file`` storage from per-frame stem to view_name (level),
but the viewport filter kept comparing against the per-frame stem, so every
room was filtered out on sunlight projects. See plan for full context.
"""

from __future__ import annotations

from archilume_app.state.editor_state import EditorState


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


def _make_sunlight_state(view_name: str, stems: list[str]) -> EditorState:
    state = object.__new__(EditorState)
    object.__setattr__(state, "dirty_vars", set())
    object.__setattr__(state, "_self_dirty_computed_vars", set())
    object.__setattr__(state, "base_state", state)

    vgs = [_view_group(view_name, stems)]
    state.view_groups = vgs
    state.current_view_idx = 0
    state.current_frame_idx = 0

    state.hdr_files = [
        {"name": f["hdr_stem"], "hdr_path": f["hdr_path"], "tiff_paths": [], "suffix": "", "legend_map": {}}
        for vg in vgs for f in vg["frames"]
    ]
    state.current_hdr_idx = 0
    state.image_width = 100
    state.image_height = 100
    state.hdr_view_params = {
        f["hdr_stem"]: [0.0, 0.0, 10.0, 10.0, 100, 100]
        for vg in vgs for f in vg["frames"]
    }
    state.room_df_results = {}
    state.annotation_scale = 1.0
    state.selected_room_idx = -1
    state.multi_selected_idxs = []
    return state


def _sample_room(view_name: str) -> dict:
    return {
        "name": "R1",
        "hdr_file": view_name,
        "world_vertices": [[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0]],
        "vertices": [],
        "visible": True,
        "parent": "",
        "room_type": "NONE",
    }


def test_enriched_rooms_visible_on_first_frame_of_level() -> None:
    state = _make_sunlight_state("ffl_090800", ["SS_0621_0900", "SS_0621_0915"])
    state.rooms = [_sample_room("ffl_090800")]
    state.current_hdr_idx = 0

    enriched = state.enriched_rooms
    assert len(enriched) == 1
    assert enriched[0]["name"] == "R1"


def test_enriched_rooms_visible_on_subsequent_frame_of_level() -> None:
    state = _make_sunlight_state("ffl_090800", ["SS_0621_0900", "SS_0621_0915"])
    state.rooms = [_sample_room("ffl_090800")]
    state.current_hdr_idx = 1

    enriched = state.enriched_rooms
    assert len(enriched) == 1, (
        "rooms keyed by view_name must render on every frame of the level, "
        "not only the first"
    )


def test_enriched_rooms_excludes_rooms_from_other_levels() -> None:
    state = _make_sunlight_state("ffl_090800", ["SS_0621_0900"])
    state.rooms = [_sample_room("ffl_093260")]
    state.current_hdr_idx = 0

    assert state.enriched_rooms == []


def test_enriched_rooms_daylight_still_keys_by_hdr_name() -> None:
    state = object.__new__(EditorState)
    object.__setattr__(state, "dirty_vars", set())
    object.__setattr__(state, "_self_dirty_computed_vars", set())
    object.__setattr__(state, "base_state", state)
    state.view_groups = []
    state.current_view_idx = 0
    state.current_frame_idx = 0
    state.hdr_files = [
        {"name": "room_A", "hdr_path": "/tmp/room_A.hdr", "tiff_paths": [], "suffix": "", "legend_map": {}},
    ]
    state.current_hdr_idx = 0
    state.image_width = 100
    state.image_height = 100
    state.hdr_view_params = {"room_A": [0.0, 0.0, 10.0, 10.0, 100, 100]}
    state.room_df_results = {}
    state.annotation_scale = 1.0
    state.selected_room_idx = -1
    state.multi_selected_idxs = []
    state.rooms = [{
        "name": "R1",
        "hdr_file": "room_A",
        "world_vertices": [[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0]],
        "vertices": [],
        "visible": True,
        "parent": "",
        "room_type": "NONE",
    }]

    assert len(state.enriched_rooms) == 1
