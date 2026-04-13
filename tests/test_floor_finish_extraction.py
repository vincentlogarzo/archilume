"""
Test: floor finish polygon extraction from OBJ models.

Two test tiers:
  - Unit tests (fast): synthetic OBJ that mimics real-world structure —
    floor faces, wall faces, and line elements (l-lines). Always run.
  - Integration test (slow, marked): uses the real BTR.obj from
    projects/527DM/inputs/. Skipped if file absent or --run-slow not passed.

Verifies:
  1. Material injection with mixed cell types (face + line elements).
  2. Floor finish polygon extraction at a known Z level.
  3. Polygon shape, vertex count, and material ID validity.
  4. Named materials appear on finish polygons (not all -1).
"""

import pytest
import numpy as np
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REAL_OBJ = Path(__file__).parent.parent / "projects" / "527DM" / "inputs" / "BTR.obj"

FLOOR_Z = 0.0
FINISH_MAT = "GL02"
WALL_MAT = "WallFinish"

# Synthetic OBJ: 3 floor faces (GL02 at z≈0), 1 angled wall face (WallFinish),
# 1 line element (l) — the exact pattern that caused the cell-count mismatch bug.
SYNTHETIC_OBJ = """\
# Synthetic test OBJ — floor finishes at z=0, wall at z=0-3, l-element
v 0 0 0
v 5 0 0
v 5 5 0
v 0 5 0
v 0 0 3
v 5 0 3
v 2 2 0.05
v 3 2 0.05
v 3 3 0.05
usemtl GL02
f 1 2 3
f 1 3 4
f 7 8 9
usemtl WallFinish
f 1 2 6 5
l 5 6
"""


@pytest.fixture(scope="module")
def synthetic_slicer(tmp_path_factory):
    """MeshSlicer loaded from the synthetic OBJ (always available)."""
    from archilume.apps.obj_aoi_editor_matplotlib import MeshSlicer
    p = tmp_path_factory.mktemp("obj") / "test.obj"
    p.write_text(SYNTHETIC_OBJ)
    return MeshSlicer(p, detect_floors=False)


# ---------------------------------------------------------------------------
# Unit tests — synthetic OBJ
# ---------------------------------------------------------------------------

class TestMaterialInjection:
    def test_names_loaded(self, synthetic_slicer):
        names = list(synthetic_slicer.mesh.field_data.get("MaterialNames", []))
        assert names, (
            "No material names injected. _inject_material_ids likely failed due to "
            "cell-count mismatch from l-line elements in the OBJ."
        )
        assert FINISH_MAT in names, f"{FINISH_MAT!r} not found; got {names}"
        assert WALL_MAT in names, f"{WALL_MAT!r} not found; got {names}"

    def test_ids_length_matches_n_cells(self, synthetic_slicer):
        mat_ids = synthetic_slicer.mesh.cell_data.get("MaterialIds")
        assert mat_ids is not None, "MaterialIds cell_data absent — injection failed."
        assert len(mat_ids) == synthetic_slicer.mesh.n_cells, (
            f"MaterialIds length {len(mat_ids)} != n_cells {synthetic_slicer.mesh.n_cells}"
        )

    def test_line_cells_get_minus_one(self, synthetic_slicer):
        """l-line element cells must have material_id == -1."""
        mat_ids = synthetic_slicer.mesh.cell_data.get("MaterialIds")
        if mat_ids is None:
            pytest.skip("MaterialIds absent")
        assert -1 in mat_ids, "Expected at least one -1 (line element) in MaterialIds."

    def test_face_ids_in_range(self, synthetic_slicer):
        names = list(synthetic_slicer.mesh.field_data.get("MaterialNames", []))
        mat_ids = synthetic_slicer.mesh.cell_data.get("MaterialIds")
        if mat_ids is None or not names:
            pytest.skip()
        face_ids = mat_ids[mat_ids >= 0]
        assert face_ids.max() < len(names), (
            f"Material ID {face_ids.max()} out of range for {len(names)} names."
        )


class TestFloorFinishExtraction:
    def test_polygons_returned_at_floor_z(self, synthetic_slicer):
        polys = synthetic_slicer.get_floor_finish_polygons(FLOOR_Z, z_band=0.3)
        assert len(polys) > 0, (
            f"No floor finish polygons at z={FLOOR_Z}. "
            "Possible: normals OOM, z_band too tight, or face-index misalignment."
        )

    def test_polygon_shape(self, synthetic_slicer):
        polys = synthetic_slicer.get_floor_finish_polygons(FLOOR_Z, z_band=0.3)
        assert polys, "No polygons to check."
        for i, (xy, mid) in enumerate(polys):
            assert isinstance(xy, np.ndarray), f"Poly {i}: xy not ndarray"
            assert xy.ndim == 2 and xy.shape[1] == 2, f"Poly {i}: shape {xy.shape} not (N,2)"
            assert xy.shape[0] >= 3, f"Poly {i}: fewer than 3 vertices"

    def test_finish_mat_appears(self, synthetic_slicer):
        """At least one polygon must carry the GL02 material ID."""
        names = list(synthetic_slicer.mesh.field_data.get("MaterialNames", []))
        if FINISH_MAT not in names:
            pytest.skip(f"{FINISH_MAT} not in material names")
        target_id = names.index(FINISH_MAT)

        polys = synthetic_slicer.get_floor_finish_polygons(FLOOR_Z, z_band=0.3)
        matching = [mid for _, mid in polys if mid == target_id]
        assert len(matching) > 0, (
            f"No polygons with material '{FINISH_MAT}' (id={target_id}) at z={FLOOR_Z}. "
            f"Got IDs: {[mid for _, mid in polys]}"
        )

    def test_wall_faces_excluded(self, synthetic_slicer):
        """Vertical wall faces must not appear in floor finish results."""
        polys = synthetic_slicer.get_floor_finish_polygons(FLOOR_Z, z_band=0.3)
        names = list(synthetic_slicer.mesh.field_data.get("MaterialNames", []))
        wall_id = names.index(WALL_MAT) if WALL_MAT in names else -99
        wall_polys = [mid for _, mid in polys if mid == wall_id]
        assert len(wall_polys) == 0, (
            f"Wall material '{WALL_MAT}' appeared in floor finish results — "
            "normal-z filter not excluding vertical faces."
        )

    def test_no_polygons_at_wrong_z(self, synthetic_slicer):
        """At a Z far from the floor (e.g. z=50), no polygons should return."""
        polys = synthetic_slicer.get_floor_finish_polygons(50.0, z_band=0.1)
        assert len(polys) == 0, (
            f"Expected 0 polygons at z=50m but got {len(polys)} — z_band filter broken."
        )


# ---------------------------------------------------------------------------
# Integration test note
# ---------------------------------------------------------------------------
# The real BTR.obj (40M faces) exceeds available RAM for pv.read() on this
# machine — VTK hard-aborts at the C level, which pytest cannot catch.
# Integration testing against the real model must be done manually:
#
#   python -c "
#   from archilume.apps.obj_aoi_editor_matplotlib import MeshSlicer
#   s = MeshSlicer('projects/527DM/inputs/BTR.obj', detect_floors=True, simplify_ratio=0.05)
#   print(s.floor_levels)
#   print(s.get_floor_finish_polygons(s.floor_levels[0])[:3])
#   "
#
# Use simplify_ratio=0.05 to keep memory under control.
