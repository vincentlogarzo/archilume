"""Tests for :mod:`archilume.geo.ifc_inspector`."""

from __future__ import annotations

from pathlib import Path

import pytest

ifcopenshell = pytest.importorskip("ifcopenshell")

from archilume.geo.ifc_inspector import IFCInspector


@pytest.fixture
def ifc_file(tmp_path) -> Path:
    f = ifcopenshell.file(schema="IFC4")
    f.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), Name="Proj")
    for i in range(3):
        f.create_entity(
            "IfcWall", GlobalId=ifcopenshell.guid.new(), Name=f"W{i}",
        )
    f.create_entity(
        "IfcDoor", GlobalId=ifcopenshell.guid.new(), Name="D1",
    )
    path = tmp_path / "min.ifc"
    f.write(str(path))
    return path


class TestIFCInspector:
    def test_init_stores_path(self, ifc_file):
        insp = IFCInspector(ifc_file)
        assert insp.filepath == Path(ifc_file)
        assert insp.ifc is None  # not loaded yet

    def test_raw_scan_counts_lines_and_classes(self, ifc_file):
        insp = IFCInspector(ifc_file)
        insp._raw_scan()
        assert insp.lines_total > 0
        # Class names come from the STEP text as uppercase tokens.
        classes = {c.upper() for c in insp.entity_class.values()}
        assert "IFCWALL" in classes
        assert "IFCDOOR" in classes

    def test_load_ifc_populates_attribute(self, ifc_file):
        insp = IFCInspector(ifc_file)
        insp._load_ifc()
        assert insp.ifc is not None

    def test_build_schema_produces_subtypes_map(self, ifc_file):
        insp = IFCInspector(ifc_file)
        insp._load_ifc()
        insp._build_schema()
        assert isinstance(insp.subtypes_map, dict)
        # Schema uses PascalCase canonical names (IfcProduct, IfcControl, ...).
        assert "IfcProduct" in insp.subtypes_map

    def test_all_subtypes_terminates(self, ifc_file):
        insp = IFCInspector(ifc_file)
        insp._load_ifc()
        insp._build_schema()
        out = insp._all_subtypes("IfcProduct")
        assert isinstance(out, set)
        # Must return at least one subtype and terminate (no infinite recursion).
        assert len(out) >= 1

    def test_has_any_data_returns_bool(self, ifc_file):
        insp = IFCInspector(ifc_file)
        insp._load_ifc()
        insp._build_schema()
        assert isinstance(insp._has_any_data("IfcWall"), bool)

    def test_parse_end_to_end(self, ifc_file):
        insp = IFCInspector(ifc_file)
        insp.parse()
        # After parse, subtypes_map is populated and raw scan done.
        assert insp.lines_total > 0
        assert insp.subtypes_map

    def test_subtree_bytes_non_negative(self, ifc_file):
        insp = IFCInspector(ifc_file)
        insp.parse()
        b = insp._subtree_bytes("IfcWall")
        assert b >= 0

    def test_subtree_count_non_negative(self, ifc_file):
        insp = IFCInspector(ifc_file)
        insp.parse()
        c = insp._subtree_count("IfcWall")
        assert c >= 0

    def test_attribute_bytes_populates_product_attr(self, ifc_file):
        insp = IFCInspector(ifc_file)
        insp.parse()
        insp._attribute_bytes()
        assert isinstance(insp.product_attr_bytes, dict)

    def test_report_runs_without_raise(self, ifc_file, capsys):
        insp = IFCInspector(ifc_file)
        insp.parse()
        insp.report()
        out = capsys.readouterr().out
        assert "File size" in out or "Total lines" in out
