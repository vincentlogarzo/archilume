"""Tests for :mod:`archilume.geo.obj_inspector`."""

from __future__ import annotations

from pathlib import Path

import pytest

from archilume.geo.obj_inspector import OBJInspector


def _obj_sample() -> str:
    """OBJ with 2 named objects under distinct IFC classes."""
    return (
        "o IfcWall/WallA\n"
        "v 0 0 0\nv 1 0 0\nv 1 1 0\n"
        "f 1 2 3\n"
        "o IfcDoor/DoorA\n"
        "v 0 0 1\nv 1 0 1\nv 1 1 1\n"
        "f 4 5 6\n"
        "vn 0 0 1\n"
        "vt 0 0\n"
    )


class TestOBJInspector:
    def test_parse_counts_elements(self, tmp_path):
        f = tmp_path / "a.obj"
        f.write_text(_obj_sample())
        insp = OBJInspector(f)
        insp.parse()
        assert insp.vertices == 6
        assert insp.faces == 2
        assert insp.objects == 2
        assert insp.normals == 1
        assert insp.textures == 1

    def test_bounding_box_captured(self, tmp_path):
        f = tmp_path / "a.obj"
        f.write_text(_obj_sample())
        insp = OBJInspector(f)
        insp.parse()
        assert insp.min_x == 0 and insp.max_x == 1
        assert insp.min_z == 0 and insp.max_z == 1

    def test_object_and_class_faces_tracked(self, tmp_path):
        f = tmp_path / "a.obj"
        f.write_text(_obj_sample())
        insp = OBJInspector(f)
        insp.parse()
        # Two named objects, each claiming one face.
        assert "IfcWall/WallA" in insp.object_faces
        assert "IfcDoor/DoorA" in insp.object_faces
        assert insp.object_faces["IfcWall/WallA"] == 1
        assert insp.object_faces["IfcDoor/DoorA"] == 1
        # Classes (first path segment) roll up.
        assert insp.class_faces.get("IfcWall") == 1
        assert insp.class_faces.get("IfcDoor") == 1

    def test_report_runs_without_raise(self, tmp_path, capsys):
        f = tmp_path / "a.obj"
        f.write_text(_obj_sample())
        insp = OBJInspector(f)
        insp.parse()
        insp.report()  # prints to stdout; just ensure no exception.
        out = capsys.readouterr().out
        assert "File size" in out
        assert "Vertices" in out
