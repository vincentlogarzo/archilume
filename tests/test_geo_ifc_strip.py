"""Tests for :mod:`archilume.geo.ifc_strip`."""

from __future__ import annotations

from pathlib import Path

import pytest

ifcopenshell = pytest.importorskip("ifcopenshell")

from archilume.geo.ifc_strip import IfcStrip


@pytest.fixture
def ifc_file(tmp_path) -> Path:
    f = ifcopenshell.file(schema="IFC4")
    f.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), Name="Proj")
    # Classes that DEFAULT_CLASSES_TO_REMOVE should drop:
    f.create_entity("IfcDoor", GlobalId=ifcopenshell.guid.new(), Name="DoorA")
    f.create_entity("IfcOpeningElement", GlobalId=ifcopenshell.guid.new(),
                    Name="OpeningA")
    # A wall with "demolish" in its name — matched by DEFAULT_NAME_PATTERNS.
    f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(),
                    Name="demolish_this_wall")
    # Keeper — an ordinary wall.
    f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="GoodWall")
    path = tmp_path / "scene.ifc"
    f.write(str(path))
    return path


class TestIfcStripInit:
    def test_default_output_path_suffixed(self, ifc_file):
        s = IfcStrip(input_path=ifc_file)
        assert s.output_path == ifc_file.with_name(ifc_file.stem + "_stripped" + ifc_file.suffix)

    def test_missing_input_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            IfcStrip(input_path=tmp_path / "missing.ifc")

    def test_explicit_output_path_honoured(self, tmp_path, ifc_file):
        dest = tmp_path / "out.ifc"
        s = IfcStrip(input_path=ifc_file, output_path=dest)
        assert s.output_path == dest

    def test_defaults_copied_not_shared(self, ifc_file):
        s1 = IfcStrip(input_path=ifc_file)
        s1.classes_to_remove.append("X")
        s2 = IfcStrip(input_path=ifc_file)
        assert "X" not in s2.classes_to_remove


class TestIfcStripLoad:
    def test_load_populates_internal_ifc(self, ifc_file):
        s = IfcStrip(input_path=ifc_file)
        s.load()
        assert s._ifc is not None


class TestIfcStripRemove:
    def test_remove_by_classes_drops_doors(self, ifc_file):
        s = IfcStrip(input_path=ifc_file)
        s.load()
        before = len(s._ifc.by_type("IfcDoor"))
        removed = s._remove_by_classes()
        after = len(s._ifc.by_type("IfcDoor"))
        assert before >= 1
        assert after == 0
        assert removed >= 1

    def test_remove_by_name_patterns_drops_demolish_wall(self, ifc_file):
        s = IfcStrip(input_path=ifc_file)
        s.load()
        names_before = {w.Name for w in s._ifc.by_type("IfcWall")}
        s._remove_by_name_patterns()
        names_after = {w.Name for w in s._ifc.by_type("IfcWall")}
        # "demolish_this_wall" matched; "GoodWall" kept.
        assert "demolish_this_wall" in names_before
        assert "demolish_this_wall" not in names_after
        assert "GoodWall" in names_after

    def test_remove_by_type_patterns_safe_on_empty_match(self, ifc_file):
        s = IfcStrip(input_path=ifc_file, type_patterns=["zzz_no_match"])
        s.load()
        # Should not raise and should return 0 removals.
        assert s._remove_by_type_patterns() == 0

    def test_purge_unused_non_negative(self, ifc_file):
        s = IfcStrip(input_path=ifc_file)
        s.load()
        s._remove_by_classes()
        purged = s._purge_unused()
        assert purged >= 0


class TestIfcStripRun:
    def test_run_writes_output_file(self, ifc_file, tmp_path):
        out = tmp_path / "out.ifc"
        s = IfcStrip(input_path=ifc_file, output_path=out)
        s.run()
        assert out.exists()

    def test_run_reduces_or_preserves_entity_count(self, ifc_file, tmp_path):
        out = tmp_path / "out.ifc"
        src = ifcopenshell.open(str(ifc_file))
        before = len(list(src))
        IfcStrip(input_path=ifc_file, output_path=out).run()
        dst = ifcopenshell.open(str(out))
        after = len(list(dst))
        # Stripping removes at least the IfcDoor + opening + demolish_wall.
        assert after <= before
