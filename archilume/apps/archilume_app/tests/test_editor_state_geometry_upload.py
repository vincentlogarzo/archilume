"""Integration tests for the sunlight geometry upload flow.

Exercises :meth:`EditorState._stage_uploaded_files` against the new
``geometry_building`` / ``geometry_site`` slots introduced when we split
the single geometry field in two. The synchronous staging helper is
called directly — no async / websocket machinery needed — and the state's
``new_project_staged`` dict is asserted alongside
``project_modes.invalid_combinations`` so both per-file validators and
cross-field pairing rules are covered.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from archilume_app.lib import project_modes as pm
from archilume_app.state.editor_state import _StagedUploadBytes


# ---------------------------------------------------------------------------
# Minimal OBJ / MTL byte payloads
# ---------------------------------------------------------------------------

def _cube_obj_bytes(side_m: float = 5.0) -> bytes:
    """Axis-aligned cube OBJ (12 triangles) with ``side_m`` edge length."""
    s = side_m
    verts = [
        (0, 0, 0), (s, 0, 0), (s, s, 0), (0, s, 0),
        (0, 0, s), (s, 0, s), (s, s, s), (0, s, s),
    ]
    faces = [
        (1, 2, 3), (1, 3, 4), (5, 6, 7), (5, 7, 8),
        (1, 2, 6), (1, 6, 5), (4, 3, 7), (4, 7, 8),
        (1, 4, 8), (1, 8, 5), (2, 3, 7), (2, 7, 6),
    ]
    lines = [f"v {x} {y} {z}" for (x, y, z) in verts]
    lines += [f"f {a} {b} {c}" for (a, b, c) in faces]
    return ("\n".join(lines) + "\n").encode("utf-8")


_MTL_BYTES = b"newmtl plaster\nKd 0.8 0.8 0.8\nd 1.0\n"


# ---------------------------------------------------------------------------
# Shared fixture: preconfigured state ready to accept uploads
# ---------------------------------------------------------------------------

@pytest.fixture
def staging_state(make_editor_state, tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    return make_editor_state(
        new_project_mode="sunlight",
        new_project_staging_dir=str(staging),
        new_project_staged={},
    )


def _stage(state, field_id: str, files: list[tuple[str, bytes]]) -> None:
    """Feed ``[(filename, bytes), ...]`` into the create-flow staging helper."""
    uploads = [_StagedUploadBytes(name=name, data=data) for name, data in files]
    state._stage_uploaded_files(field_id, uploads, "create")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestValidPairs:
    def test_matching_obj_and_mtl_both_ok(self, staging_state):
        _stage(staging_state, "geometry_building", [
            ("building.obj", _cube_obj_bytes()),
            ("building.mtl", _MTL_BYTES),
        ])
        entries = staging_state.new_project_staged["geometry_building"]
        assert len(entries) == 2
        assert all(e["ok"] for e in entries), entries
        assert pm.invalid_combinations("sunlight", staging_state.new_project_staged) == []

    def test_building_and_site_slots_independent(self, staging_state):
        _stage(staging_state, "geometry_building", [
            ("bld.obj", _cube_obj_bytes()),
            ("bld.mtl", _MTL_BYTES),
        ])
        _stage(staging_state, "geometry_site", [
            ("site.obj", _cube_obj_bytes(side_m=20.0)),
            ("site.mtl", _MTL_BYTES),
        ])
        assert pm.invalid_combinations("sunlight", staging_state.new_project_staged) == []


# ---------------------------------------------------------------------------
# Pairing rules (invalid_combinations)
# ---------------------------------------------------------------------------

class TestPairingRules:
    def test_obj_without_mtl_flags_missing_sibling(self, staging_state):
        _stage(staging_state, "geometry_building", [
            ("lonely.obj", _cube_obj_bytes()),
        ])
        errors = pm.invalid_combinations("sunlight", staging_state.new_project_staged)
        assert any("lonely.mtl" in e for e in errors), errors

    def test_mtl_without_obj_flags_missing_obj(self, staging_state):
        _stage(staging_state, "geometry_building", [
            ("orphan.mtl", _MTL_BYTES),
        ])
        errors = pm.invalid_combinations("sunlight", staging_state.new_project_staged)
        assert any("without a matching .obj" in e for e in errors), errors

    def test_stem_mismatch_is_reported(self, staging_state):
        _stage(staging_state, "geometry_building", [
            ("foo.obj", _cube_obj_bytes()),
            ("bar.mtl", _MTL_BYTES),
        ])
        errors = pm.invalid_combinations("sunlight", staging_state.new_project_staged)
        assert any("different stems" in e for e in errors), errors

    def test_two_objs_in_one_slot_flagged(self, staging_state):
        _stage(staging_state, "geometry_building", [
            ("a.obj", _cube_obj_bytes()),
            ("a.mtl", _MTL_BYTES),
            ("b.obj", _cube_obj_bytes(side_m=3.0)),
        ])
        errors = pm.invalid_combinations("sunlight", staging_state.new_project_staged)
        assert any("exactly one .obj" in e for e in errors), errors


# ---------------------------------------------------------------------------
# Per-file dispatch: .obj and .mtl are routed to different validators
# ---------------------------------------------------------------------------

class TestExtensionDispatch:
    def test_mtl_is_not_rejected_as_missing_faces(self, staging_state):
        """Regression guard: before extension_validators, uploading a .mtl to
        the geometry field ran ``validate_obj`` on it and reported 'no faces'."""
        _stage(staging_state, "geometry_building", [
            ("building.mtl", _MTL_BYTES),
        ])
        entries = staging_state.new_project_staged["geometry_building"]
        assert len(entries) == 1
        assert entries[0]["ok"] is True
        assert entries[0]["error"] == ""

    def test_millimetre_scaled_obj_rejected_with_unit_hint(self, staging_state):
        _stage(staging_state, "geometry_building", [
            ("mm_export.obj", _cube_obj_bytes(side_m=50_000.0)),
        ])
        entry = staging_state.new_project_staged["geometry_building"][0]
        assert entry["ok"] is False
        assert "units" in entry["error"].lower() or "millimetres" in entry["error"].lower()

    def test_vertices_only_obj_rejected_with_faces_hint(self, staging_state, tmp_path):
        verts_obj = "\n".join(
            f"v {i} 0 0" for i in range(1, 10)
        ).encode("utf-8")
        _stage(staging_state, "geometry_building", [
            ("verts.obj", verts_obj),
        ])
        entry = staging_state.new_project_staged["geometry_building"][0]
        assert entry["ok"] is False
        assert "faces" in entry["error"].lower()


# ---------------------------------------------------------------------------
# Settings-modal file partitioning heuristic
# ---------------------------------------------------------------------------

class TestGeometrySlotOwnership:
    def test_site_filename_assigned_to_site_slot(self):
        from archilume_app.state.editor_state import _geometry_slot_owns
        assert _geometry_slot_owns("geometry_site", "87cowles_site_decimated.obj")
        assert not _geometry_slot_owns("geometry_building", "87cowles_site_decimated.obj")

    def test_shading_filename_assigned_to_site_slot(self):
        from archilume_app.state.editor_state import _geometry_slot_owns
        assert _geometry_slot_owns("geometry_site", "near_shading.obj")
        assert not _geometry_slot_owns("geometry_building", "near_shading.obj")

    def test_plain_filename_assigned_to_building_slot(self):
        from archilume_app.state.editor_state import _geometry_slot_owns
        assert _geometry_slot_owns("geometry_building", "87Cowles_BLD_withWindows.obj")
        assert not _geometry_slot_owns("geometry_site", "87Cowles_BLD_withWindows.obj")

    def test_non_geometry_field_passes_through(self):
        from archilume_app.state.editor_state import _geometry_slot_owns
        assert _geometry_slot_owns("pdf", "anything.pdf")
