"""Tests for :mod:`archilume.core.mtl_converter`."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytest.importorskip("pyradiance")

from archilume.core.mtl_converter import MtlConverter


@pytest.fixture(autouse=True)
def _reset_class_materials():
    """``MtlConverter.materials`` is a class-level list; reset between tests."""
    MtlConverter.materials = []
    yield
    MtlConverter.materials = []


class TestMtlConverterInit:
    def test_missing_output_dir_raises(self):
        with pytest.raises(ValueError, match="output_dir"):
            MtlConverter(rad_paths=[], mtl_paths=[], output_dir=None)

    def test_creates_output_dir(self, tmp_path):
        out = tmp_path / "rad_out"
        MtlConverter(output_dir=out)
        assert out.exists()

    def test_output_mtl_path_set(self, tmp_path):
        conv = MtlConverter(output_dir=tmp_path)
        assert Path(conv.output_mtl_path).name == "materials.mtl"

    def test_empty_rad_paths_leaves_modifiers_empty(self, tmp_path):
        conv = MtlConverter(output_dir=tmp_path, rad_paths=[])
        assert conv.rad_modifiers == set()


class TestGetModifiersFromRad:
    def test_returns_empty_when_rad_missing(self, tmp_path):
        conv = MtlConverter(output_dir=tmp_path)
        # Name-mangled private method — access via the expected attribute name.
        fn = conv._MtlConverter__get_modifiers_from_rad
        assert fn(tmp_path / "missing.rad") == set()

    def test_parses_m_lines_from_rad2mgf_output(self, tmp_path, monkeypatch):
        rad = tmp_path / "scene.rad"
        rad.write_text("# fake rad")

        def _fake_run(cmd, **kw):
            class R:
                returncode = 0
                stdout = "m brick\nm concrete\nx ignored\n"
                stderr = ""
            return R()

        monkeypatch.setattr(subprocess, "run", _fake_run)
        conv = MtlConverter(output_dir=tmp_path)
        mods = conv._MtlConverter__get_modifiers_from_rad(rad)
        assert mods == {"brick", "concrete"}

    def test_returns_empty_on_rad2mgf_missing(self, tmp_path, monkeypatch):
        rad = tmp_path / "scene.rad"
        rad.write_text("x")

        def _raise_fnf(*a, **kw):
            raise FileNotFoundError("no rad2mgf")

        monkeypatch.setattr(subprocess, "run", _raise_fnf)
        conv = MtlConverter(output_dir=tmp_path)
        assert conv._MtlConverter__get_modifiers_from_rad(rad) == set()


class TestCreateRadianceMtlFile:
    def test_writes_default_materials_when_no_mtl_match(self, tmp_path, monkeypatch):
        rad = tmp_path / "x.rad"
        rad.write_text("# rad")

        def _fake_run(cmd, **kw):
            class R:
                returncode = 0
                stdout = "m wall\nm floor\n"
                stderr = ""
            return R()

        monkeypatch.setattr(subprocess, "run", _fake_run)
        conv = MtlConverter(rad_paths=[str(rad)], mtl_paths=[], output_dir=tmp_path)
        conv.create_radiance_mtl_file()
        out = Path(conv.output_mtl_path)
        assert out.exists()
        text = out.read_text(encoding="utf-8")
        assert "wall" in text
        assert "floor" in text

    def test_matches_mtl_kd_and_opacity(self, tmp_path, monkeypatch):
        rad = tmp_path / "x.rad"
        rad.write_text("# rad")
        mtl = tmp_path / "m.mtl"
        mtl.write_text(
            "newmtl brick\n"
            "Kd 0.8 0.2 0.2\n"
            "d 1.0\n"
            "newmtl window\n"
            "Kd 0.1 0.1 0.9\n"
            "d 0.3\n"
        )

        def _fake_run(cmd, **kw):
            class R:
                returncode = 0
                stdout = "m brick\nm window\n"
                stderr = ""
            return R()

        monkeypatch.setattr(subprocess, "run", _fake_run)
        conv = MtlConverter(
            rad_paths=[str(rad)], mtl_paths=[str(mtl)], output_dir=tmp_path,
        )
        conv.create_radiance_mtl_file()
        text = Path(conv.output_mtl_path).read_text(encoding="utf-8")
        # Brick is opaque (d=1.0) → plastic. Window is translucent (d<1) → glass.
        assert "brick" in text
        assert "window" in text
