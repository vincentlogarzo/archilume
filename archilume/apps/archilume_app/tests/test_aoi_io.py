"""Tests for archilume_app.lib.aoi_io — v2 .aoi writer, rename, delete."""

from __future__ import annotations

from pathlib import Path

import pytest

from archilume_app.lib import aoi_io


class TestSanitizeStem:
    def test_plain_name_unchanged(self):
        assert aoi_io.sanitize_stem("U101_T") == "U101_T"

    def test_spaces_collapsed(self):
        assert aoi_io.sanitize_stem("3 BED") == "3_BED"

    def test_special_chars_dropped(self):
        assert aoi_io.sanitize_stem("U101/Bed#1") == "U101Bed1"

    def test_empty_falls_back(self):
        assert aoi_io.sanitize_stem("") == "room"
        assert aoi_io.sanitize_stem("!!!") == "room"


class TestWriteV2Aoi:
    def test_writes_header_and_vertices(self, tmp_path: Path):
        verts = [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)]
        out = aoi_io.write_v2_aoi(tmp_path, "U101_T", 93.26, verts)
        assert out == tmp_path / "U101_T.aoi"
        text = out.read_text(encoding="utf-8")
        lines = text.splitlines()
        assert lines[0] == "AoI Points File : X,Y positions"
        assert lines[1].startswith("FFL z height(m): 93.2600")
        assert lines[2] == "POINTS 4"
        assert lines[3] == "0.0000 0.0000"
        assert lines[6] == "0.0000 5.0000"

    def test_sanitizes_filename(self, tmp_path: Path):
        out = aoi_io.write_v2_aoi(tmp_path, "3 BED", 10.0, [(0, 0), (1, 0), (1, 1)])
        assert out.name == "3_BED.aoi"

    def test_rejects_fewer_than_three_vertices(self, tmp_path: Path):
        with pytest.raises(ValueError):
            aoi_io.write_v2_aoi(tmp_path, "R", 0.0, [(0, 0), (1, 0)])

    def test_overwrites_existing(self, tmp_path: Path):
        verts = [(0, 0), (1, 0), (1, 1)]
        aoi_io.write_v2_aoi(tmp_path, "R", 1.0, verts)
        aoi_io.write_v2_aoi(tmp_path, "R", 2.0, verts)
        content = (tmp_path / "R.aoi").read_text(encoding="utf-8")
        assert "FFL z height(m): 2.0000" in content

    def test_creates_dest_dir(self, tmp_path: Path):
        dest = tmp_path / "nested" / "aoi"
        aoi_io.write_v2_aoi(dest, "R", 0.0, [(0, 0), (1, 0), (1, 1)])
        assert (dest / "R.aoi").exists()


class TestDeleteAoi:
    def test_removes_existing(self, tmp_path: Path):
        aoi_io.write_v2_aoi(tmp_path, "R", 0.0, [(0, 0), (1, 0), (1, 1)])
        assert aoi_io.delete_aoi(tmp_path, "R") is True
        assert not (tmp_path / "R.aoi").exists()

    def test_noop_when_missing(self, tmp_path: Path):
        assert aoi_io.delete_aoi(tmp_path, "ghost") is False


class TestRenameAoi:
    def test_renames_existing(self, tmp_path: Path):
        aoi_io.write_v2_aoi(tmp_path, "old", 0.0, [(0, 0), (1, 0), (1, 1)])
        assert aoi_io.rename_aoi(tmp_path, "old", "new") is True
        assert not (tmp_path / "old.aoi").exists()
        assert (tmp_path / "new.aoi").exists()

    def test_noop_when_src_missing(self, tmp_path: Path):
        assert aoi_io.rename_aoi(tmp_path, "ghost", "new") is False
        assert not (tmp_path / "new.aoi").exists()

    def test_same_name_returns_existence(self, tmp_path: Path):
        assert aoi_io.rename_aoi(tmp_path, "R", "R") is False
        aoi_io.write_v2_aoi(tmp_path, "R", 0.0, [(0, 0), (1, 0), (1, 1)])
        assert aoi_io.rename_aoi(tmp_path, "R", "R") is True
