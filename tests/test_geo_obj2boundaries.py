"""Tests for :mod:`archilume.geo.obj2boundaries`."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from archilume.geo import obj2boundaries as ob


def _unit_cube_obj() -> str:
    """Single-cube OBJ — 8 vertices, bbox 0..1 in each axis."""
    return (
        "o cube\n"
        "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\n"
        "v 0 0 1\nv 1 0 1\nv 1 1 1\nv 0 1 1\n"
        "f 1 2 3 4\nf 5 6 7 8\n"
    )


class TestParseObjBoundingBox:
    def test_extracts_min_max_per_axis(self, tmp_path):
        f = tmp_path / "cube.obj"
        f.write_text(_unit_cube_obj())
        bbox = ob.parse_obj_bounding_box(f)
        assert bbox["x_min"] == 0 and bbox["x_max"] == 1
        assert bbox["y_min"] == 0 and bbox["y_max"] == 1
        assert bbox["z_min"] == 0 and bbox["z_max"] == 1

    def test_reports_element_counts(self, tmp_path):
        f = tmp_path / "cube.obj"
        f.write_text(_unit_cube_obj())
        bbox = ob.parse_obj_bounding_box(f)
        assert bbox["vertices"] == 8
        assert bbox["faces"] == 2

    def test_empty_obj_raises(self, tmp_path):
        f = tmp_path / "empty.obj"
        f.write_text("# nothing here\n")
        with pytest.raises(ValueError):
            ob.parse_obj_bounding_box(f)

    def test_computes_center_and_dimensions(self, tmp_path):
        f = tmp_path / "cube.obj"
        f.write_text(_unit_cube_obj())
        bbox = ob.parse_obj_bounding_box(f)
        assert bbox["center"] == (0.5, 0.5, 0.5)
        assert bbox["width"] == 1.0
        assert bbox["height"] == 1.0
        assert bbox["depth"] == 1.0


class TestGenerateRoomBoundaries:
    def test_writes_one_row_per_level(self, tmp_path):
        bbox = {
            "x_min": 0, "x_max": 10, "y_min": 0, "y_max": 10,
            "z_min": 0, "z_max": 6,  # 3 levels at 3m spacing: 0, 3, 6
        }
        out = tmp_path / "rooms.csv"
        rows = ob.generate_room_boundaries(bbox, level_height=3.0, output_path=out)
        assert out.exists()
        assert len(rows) == 3

    def test_row_format_has_level_id_and_room_type(self, tmp_path):
        bbox = {
            "x_min": 0, "x_max": 1, "y_min": 0, "y_max": 1,
            "z_min": 0, "z_max": 3,
        }
        out = tmp_path / "rooms.csv"
        rows = ob.generate_room_boundaries(
            bbox, level_height=3.0, output_path=out,
            room_type="LIVING", level_prefix="Lvl",
        )
        assert rows[0][0] == "Lvl01"
        assert rows[0][1] == "LIVING"
        # Total column count (level_id + room_type + 26 point slots) = 28.
        assert len(rows[0]) == 28

    def test_coordinate_scale_applied(self, tmp_path):
        bbox = {
            "x_min": 0, "x_max": 1, "y_min": 0, "y_max": 1,
            "z_min": 0, "z_max": 0,
        }
        out = tmp_path / "rooms.csv"
        rows = ob.generate_room_boundaries(
            bbox, level_height=3.0, output_path=out, coordinate_scale=1000.0,
        )
        # x_max=1 * 1000 = 1000.000 should appear in at least one point column.
        row0_text = " ".join(str(c) for c in rows[0])
        assert "1000.000" in row0_text

    def test_generated_csv_parses_back(self, tmp_path):
        bbox = {
            "x_min": 0, "x_max": 1, "y_min": 0, "y_max": 1,
            "z_min": 0, "z_max": 6,
        }
        out = tmp_path / "rooms.csv"
        ob.generate_room_boundaries(bbox, level_height=3.0, output_path=out)
        with open(out) as f:
            parsed = list(csv.reader(f))
        assert len(parsed) == 3
        assert all(row[1] == "FLOOR" for row in parsed)


class TestMain:
    def test_raises_when_obj_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ob.main(tmp_path / "missing.obj")

    def test_end_to_end_writes_default_csv(self, tmp_path):
        obj = tmp_path / "scene.obj"
        obj.write_text(_unit_cube_obj())
        ob.main(obj, level_height=0.5)
        default_out = tmp_path / "scene_room_boundaries.csv"
        assert default_out.exists()
