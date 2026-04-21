"""Tests for :mod:`archilume.core.radiance_materials` — Primitive factories."""

from __future__ import annotations

from pathlib import Path

import pytest

pyrad = pytest.importorskip("pyradiance")

from archilume.core import radiance_materials as rm


class TestPlasticMaterial:
    def test_defaults_produce_plastic_primitive(self):
        p = rm.create_plastic_material("wall")
        assert p.ptype == "plastic"
        assert p.identifier == "wall"
        # fargs = [kd_r, kd_g, kd_b, ks, roughness]
        assert len(p.fargs) == 5

    def test_custom_kd_passed_through(self):
        p = rm.create_plastic_material("red_wall", kd=[0.9, 0.1, 0.1])
        assert list(p.fargs[:3]) == pytest.approx([0.9, 0.1, 0.1])

    def test_custom_modifier(self):
        p = rm.create_plastic_material("w", modifier="void")
        assert p.modifier == "void"


class TestMetalMaterial:
    def test_metal_ptype_and_args(self):
        p = rm.create_metal_material("chrome", kd=[0.9, 0.9, 0.9], ks=0.95)
        assert p.ptype == "metal"
        assert len(p.fargs) == 5
        assert p.fargs[3] == pytest.approx(0.95)


class TestGlassMaterial:
    def test_glass_ptype_and_args(self):
        p = rm.create_glass_material("window", transmission=[0.9, 0.9, 0.9])
        assert p.ptype == "glass"
        assert len(p.fargs) == 3
        assert list(p.fargs) == pytest.approx([0.9, 0.9, 0.9])


class TestMirrorMaterial:
    def test_mirror_ptype_and_args(self):
        p = rm.create_mirror_material("m", rgb_reflectance=[1.0, 1.0, 1.0])
        assert p.ptype == "mirror"
        assert list(p.fargs) == pytest.approx([1.0, 1.0, 1.0])


class TestAntimatterMaterial:
    def test_antimatter_has_no_fargs(self):
        p = rm.create_antimatter_material("black_hole")
        assert p.ptype == "antimatter"
        assert list(p.fargs) == []


class TestExportMaterialsToFile:
    def test_writes_all_materials(self, tmp_path):
        mats = [
            rm.create_plastic_material("a"),
            rm.create_glass_material("b"),
            rm.create_mirror_material("c"),
        ]
        out = tmp_path / "lib.rad"
        rm.export_materials_to_file(mats, str(out))
        text = out.read_text(encoding="utf-8")
        # Header comment + each identifier should appear.
        assert "Radiance Material Library" in text
        for name in ("a", "b", "c"):
            assert name in text

    def test_empty_list_still_writes_header(self, tmp_path):
        out = tmp_path / "empty.rad"
        rm.export_materials_to_file([], str(out))
        assert "Radiance Material Library" in out.read_text(encoding="utf-8")
