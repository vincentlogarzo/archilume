"""Drawn-room → .aoi writeback contract.

Verifies that EditorState._write_aoi_for_room / _delete_aoi_for_room /
_rename_aoi_for_room honour the sunlight-only, top-level-only rule:

    parent is None → .aoi file in aoi_inputs_dir (kept in sync).
    parent set    → session-only; no .aoi file written.

The state object is built without running rx.State.__init__ (same pattern as
``test_room_hierarchy._make_state``). ``_aoi_inputs_dir_for_writeback`` is
redirected to a tmp path so tests never touch a real project directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pytest

from archilume_app.state.editor_state import EditorState


def _make_state(
    aoi_dir: Optional[Path],
    project_mode: str = "sunlight",
) -> EditorState:
    state = object.__new__(EditorState)
    object.__setattr__(state, "dirty_vars", set())
    object.__setattr__(state, "_self_dirty_computed_vars", set())
    object.__setattr__(state, "base_state", state)
    object.__setattr__(state, "rooms", [])
    object.__setattr__(state, "project", "test-project")
    object.__setattr__(state, "project_mode", project_mode)
    object.__setattr__(state, "hdr_view_params", {})
    # Redirect writeback target to the test-owned temp dir.
    object.__setattr__(
        state,
        "_aoi_inputs_dir_for_writeback",
        lambda: aoi_dir,
    )
    return state


def _room(name: str, parent: Optional[str] = None, **extra: Any) -> dict:
    base = {
        "name": name,
        "parent": parent,
        "vertices": [[0, 0], [1, 0], [1, 1]],
        "world_vertices": [[0.0, 0.0], [10.0, 0.0], [10.0, 5.0]],
        "ffl": 93.26,
        "hdr_file": "plan_ffl_093260.hdr",
    }
    base.update(extra)
    return base


class TestWriteAoiForRoom:
    def test_top_level_room_writes_file(self, tmp_path: Path):
        state = _make_state(tmp_path)
        room = _room("U101_T")
        state._write_aoi_for_room(room)
        out = tmp_path / "U101_T.aoi"
        assert out.exists()
        assert out.read_text(encoding="utf-8").startswith("AoI Points File : X,Y positions")

    def test_child_room_is_ignored(self, tmp_path: Path):
        state = _make_state(tmp_path)
        room = _room("T1", parent="U101_T")
        state._write_aoi_for_room(room)
        assert list(tmp_path.glob("*.aoi")) == []

    def test_non_sunlight_mode_is_ignored(self, tmp_path: Path):
        state = _make_state(tmp_path, project_mode="daylight")
        # Override the patched helper: for daylight the real impl returns None.
        object.__setattr__(state, "_aoi_inputs_dir_for_writeback", lambda: None)
        state._write_aoi_for_room(_room("U101_T"))
        assert list(tmp_path.glob("*.aoi")) == []

    def test_missing_ffl_and_no_hdr_is_ignored(self, tmp_path: Path):
        state = _make_state(tmp_path)
        room = _room("U101_T")
        room.pop("ffl")
        room["hdr_file"] = ""
        state._write_aoi_for_room(room)
        assert list(tmp_path.glob("*.aoi")) == []


class TestDeleteAoiForRoom:
    def test_deletes_existing(self, tmp_path: Path):
        state = _make_state(tmp_path)
        state._write_aoi_for_room(_room("U101_T"))
        assert (tmp_path / "U101_T.aoi").exists()
        state._delete_aoi_for_room("U101_T")
        assert not (tmp_path / "U101_T.aoi").exists()

    def test_noop_when_absent(self, tmp_path: Path):
        state = _make_state(tmp_path)
        state._delete_aoi_for_room("ghost")  # does not raise


class TestRenameAoiForRoom:
    def test_renames_existing(self, tmp_path: Path):
        state = _make_state(tmp_path)
        state._write_aoi_for_room(_room("old"))
        state._rename_aoi_for_room("old", "new")
        assert not (tmp_path / "old.aoi").exists()
        assert (tmp_path / "new.aoi").exists()

    def test_noop_when_same_name(self, tmp_path: Path):
        state = _make_state(tmp_path)
        state._write_aoi_for_room(_room("R"))
        state._rename_aoi_for_room("R", "R")
        assert (tmp_path / "R.aoi").exists()


class TestPixelsToWorldRoundTrip:
    def test_projection_inverts(self):
        """_project_world_to_pixels then _project_pixels_to_world is identity."""
        world = [[0.0, 0.0], [10.0, 0.0], [10.0, 5.0], [0.0, 5.0]]
        vp_x, vp_y, vh, vv, iw, ih = 5.0, 2.5, 20.0, 10.0, 800.0, 400.0
        pixels = EditorState._project_world_to_pixels(world, vp_x, vp_y, vh, vv, iw, ih)
        back = EditorState._project_pixels_to_world(pixels, vp_x, vp_y, vh, vv, iw, ih)
        for (ox, oy), (rx, ry) in zip(world, back):
            assert rx == pytest.approx(ox, abs=1e-9)
            assert ry == pytest.approx(oy, abs=1e-9)
