"""Tests for the v2 ``.aoi`` format: parser and validator.

Context: sunlight-project input ``.aoi`` files were simplified to drop
PARENT/CHILD/CENTRAL header lines. The filestem now carries the room name.
See ``C:/Users/VincentLogarzo/.claude/plans/the-room-names-are-flickering-turtle.md``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from archilume.apps.archilume_app.archilume_app.lib.project_validators import validate_aoi
from archilume.core.view_generator import ViewGenerator


# ---------- fixtures ----------

V2_CONTENT = (
    "AoI Points File : X,Y positions\n"
    "FFL z height(m): 93.260\n"
    "POINTS 4\n"
    "0.0000 0.0000\n"
    "10.0000 0.0000\n"
    "10.0000 5.0000\n"
    "0.0000 5.0000\n"
)


@pytest.fixture
def aoi_dir(tmp_path: Path) -> Path:
    d = tmp_path / "inputs" / "aoi"
    d.mkdir(parents=True)
    return d


# ---------- Parser ----------

class TestReadAoiFile:
    def test_v2_round_trip(self, aoi_dir: Path) -> None:
        path = aoi_dir / "U101_T1.aoi"
        path.write_text(V2_CONTENT, encoding="utf-8")

        name, ffl, verts = ViewGenerator._ViewGenerator__read_aoi_file(path)

        assert name == "U101_T1"
        assert ffl == pytest.approx(93.260)
        assert len(verts) == 4
        assert verts[0] == (0.0, 0.0)

    def test_missing_ffl_raises(self, aoi_dir: Path) -> None:
        path = aoi_dir / "bad.aoi"
        path.write_text("AoI Points File : X,Y positions\nPOINTS 3\n0 0\n1 0\n0 1\n", encoding="utf-8")
        with pytest.raises(ValueError, match="FFL"):
            ViewGenerator._ViewGenerator__read_aoi_file(path)

    def test_missing_points_raises(self, aoi_dir: Path) -> None:
        path = aoi_dir / "bad.aoi"
        path.write_text("AoI Points File : X,Y positions\nFFL z height(m): 1.0\n0 0\n1 0\n", encoding="utf-8")
        with pytest.raises(ValueError, match="POINTS"):
            ViewGenerator._ViewGenerator__read_aoi_file(path)


# ---------- Validator ----------

class TestValidateAoi:
    def test_v2_accepted(self, aoi_dir: Path) -> None:
        path = aoi_dir / "r.aoi"
        path.write_text(V2_CONTENT, encoding="utf-8")
        ok, msg = validate_aoi(path)
        assert ok, msg

    def test_missing_header_rejected(self, aoi_dir: Path) -> None:
        path = aoi_dir / "r.aoi"
        path.write_text("random content\nFFL z height(m): 1.0\nPOINTS 3\n0 0\n1 0\n0 1\n", encoding="utf-8")
        ok, msg = validate_aoi(path)
        assert not ok and "header" in msg.lower()

    def test_missing_ffl_rejected(self, aoi_dir: Path) -> None:
        path = aoi_dir / "r.aoi"
        path.write_text("AoI Points File : X,Y positions\nPOINTS 3\n0 0\n1 0\n0 1\n", encoding="utf-8")
        ok, msg = validate_aoi(path)
        assert not ok and "FFL" in msg

    def test_too_few_rows_rejected(self, aoi_dir: Path) -> None:
        path = aoi_dir / "r.aoi"
        path.write_text(
            "AoI Points File : X,Y positions\nFFL z height(m): 1.0\nPOINTS 2\n0 0\n1 0\n",
            encoding="utf-8",
        )
        ok, msg = validate_aoi(path)
        assert not ok and "coordinate rows" in msg
