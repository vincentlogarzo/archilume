"""Tests for :mod:`archilume.core.objs2octree`."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytest.importorskip("pyradiance")

from archilume.core.objs2octree import Objs2Octree


@pytest.fixture
def obj_files(tmp_path) -> list[Path]:
    obj = tmp_path / "scene.obj"
    obj.write_text(
        "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1 2 3 4\n"
    )
    mtl = tmp_path / "scene.mtl"
    mtl.write_text("newmtl def\nKd 0.5 0.5 0.5\nd 1.0\n")
    return [obj]


class TestObjs2OctreeInit:
    def test_wraps_single_path_in_list(self, tmp_path, obj_files):
        octree = Objs2Octree(
            input_obj_paths=obj_files[0],
            output_dir=tmp_path / "out",
            rad_dir=tmp_path / "rad",
        )
        assert isinstance(octree.input_obj_paths, list)
        assert octree.input_obj_paths[0] == obj_files[0]

    def test_derives_mtl_paths_from_obj_paths(self, tmp_path, obj_files):
        octree = Objs2Octree(
            input_obj_paths=obj_files,
            output_dir=tmp_path / "out",
            rad_dir=tmp_path / "rad",
        )
        assert octree.input_mtl_paths == [obj_files[0].with_suffix(".mtl")]

    def test_creates_output_dir(self, tmp_path, obj_files):
        out = tmp_path / "new_out"
        Objs2Octree(
            input_obj_paths=obj_files,
            output_dir=out, rad_dir=tmp_path / "rad",
        )
        assert out.exists()


class TestCreateSkyelessOctree:
    def test_short_circuits_when_octree_exists(self, tmp_path, obj_files, capsys):
        out = tmp_path / "out"
        out.mkdir()
        # Pre-seed the expected octree file.
        stem = obj_files[0].stem
        (out / f"{stem}_with_site_skyless.oct").write_bytes(b"existing")

        octree = Objs2Octree(
            input_obj_paths=obj_files, output_dir=out, rad_dir=tmp_path / "rad",
        )
        octree.create_skyless_octree_for_analysis()
        assert "already exists" in capsys.readouterr().out

    def test_runs_full_pipeline_with_mocked_subprocess(
        self, tmp_path, obj_files, monkeypatch
    ):
        out = tmp_path / "out"
        rad_dir = tmp_path / "rad"
        rad_dir.mkdir()

        def _fake_run(cmd, **kw):
            class R:
                returncode = 0
                stdout = ""
                stderr = b""
            # Simulate obj2rad writing to stdout.
            if "stdout" in kw and hasattr(kw["stdout"], "write"):
                kw["stdout"].write(b"# fake rad content\n")
            return R()

        monkeypatch.setattr(subprocess, "run", _fake_run)

        # Provide an MTL file so MtlConverter has something to read.
        (rad_dir / "scene.rad").write_text("# rad")

        octree = Objs2Octree(
            input_obj_paths=obj_files, output_dir=out, rad_dir=rad_dir,
        )
        octree.create_skyless_octree_for_analysis()
        # After the pipeline runs, output_rad_paths should be populated.
        assert len(octree.output_rad_paths) == 1


class TestObj2RadWithOsSystem:
    def test_returns_zero_on_success(self, tmp_path, obj_files, monkeypatch):
        rad_dir = tmp_path / "rad"
        rad_dir.mkdir()

        def _fake_run(cmd, **kw):
            class R:
                returncode = 0
                stderr = b""
            return R()

        monkeypatch.setattr(subprocess, "run", _fake_run)
        octree = Objs2Octree(
            input_obj_paths=obj_files,
            output_dir=tmp_path / "out", rad_dir=rad_dir,
        )
        rc = octree._Objs2Octree__obj2rad_with_os_system()
        assert rc == 0
        assert len(octree.output_rad_paths) == 1

    def test_returns_error_code_on_failure(self, tmp_path, obj_files, monkeypatch):
        rad_dir = tmp_path / "rad"
        rad_dir.mkdir()

        def _fake_run(cmd, **kw):
            class R:
                returncode = 7
                stderr = b"some error"
            return R()

        monkeypatch.setattr(subprocess, "run", _fake_run)
        octree = Objs2Octree(
            input_obj_paths=obj_files,
            output_dir=tmp_path / "out", rad_dir=rad_dir,
        )
        rc = octree._Objs2Octree__obj2rad_with_os_system()
        assert rc == 7


class TestRad2Octree:
    def test_noop_without_rad_or_mtl(self, tmp_path, obj_files, capsys):
        octree = Objs2Octree(
            input_obj_paths=obj_files,
            output_dir=tmp_path / "out", rad_dir=tmp_path / "rad",
        )
        # No output_rad_paths populated → early return with print.
        octree._Objs2Octree__rad2octree()
        assert "No RAD files" in capsys.readouterr().out

    def test_invokes_oconv_when_inputs_present(self, tmp_path, obj_files, monkeypatch):
        rad_dir = tmp_path / "rad"
        rad_dir.mkdir()
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        rad = rad_dir / "scene.rad"
        rad.write_text("")
        mtl_rad = rad_dir / "materials.mtl"
        mtl_rad.write_text("")

        captured = {}

        def _fake_run(cmd, **kw):
            captured["cmd"] = cmd

            class R:
                returncode = 0
                stdout = ""
                stderr = ""
            return R()

        monkeypatch.setattr(subprocess, "run", _fake_run)

        octree = Objs2Octree(
            input_obj_paths=obj_files, output_dir=out_dir, rad_dir=rad_dir,
        )
        octree.output_rad_paths = [rad]
        octree.combined_radiance_mtl_path = str(mtl_rad)
        octree.skyless_octree_path = out_dir / "scene_with_site_skyless.oct"
        octree._Objs2Octree__rad2octree()
        assert "oconv" in captured["cmd"]
