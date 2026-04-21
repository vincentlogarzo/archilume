"""Tests for :mod:`archilume.core.view_generator`.

Extends the existing ``test_sky_generator`` / ``test_aoi_v2`` coverage by
exercising ``ViewGenerator`` construction, CSV / AOI parsing, floor-level
grouping, and view-file emission.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from archilume.core.view_generator import ViewGenerator


def _make_rb_csv(path: Path) -> None:
    """Minimal room_boundaries CSV with two levels × 4 corner points each."""
    rows = [
        # apartment_no, room, then coordinate strings (mm)
        ["A1", "BED",
         "X_0 Y_0 Z_0",
         "X_5000 Y_0 Z_0",
         "X_5000 Y_5000 Z_0",
         "X_0 Y_5000 Z_0"],
        ["A1", "LIVING",
         "X_0 Y_0 Z_3000",
         "X_5000 Y_0 Z_3000",
         "X_5000 Y_5000 Z_3000",
         "X_0 Y_5000 Z_3000"],
    ]
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        for row in rows:
            writer.writerow(row)


def _make_v2_aoi(path: Path, ffl_m: float, verts: list[tuple[float, float]]) -> None:
    """Write a v2-format .aoi file that `__read_aoi_file` can parse."""
    lines = [
        f"AOI Points File: {path.stem}",
        "ASSOCIATED VIEW FILE: plan_ffl_xx.vp",
        f"FFL z height(m): {ffl_m}",
        "CENTRAL x,y: 0 0",
        f"POINTS {len(verts)}:",
    ]
    for x, y in verts:
        lines.append(f"{x} {y}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def view_gen(tmp_path) -> ViewGenerator:
    csv_path = tmp_path / "boundaries.csv"
    _make_rb_csv(csv_path)
    return ViewGenerator(
        room_boundaries_csv_path=csv_path,
        ffl_offset=1.2,
        view_file_dir=tmp_path / "views",
        aoi_dir=tmp_path / "aoi",
    )


class TestViewGeneratorInit:
    def test_builds_bounding_box_and_centre(self, view_gen):
        # bbox is 0..5 in x/y, 0..3 in z → centre 2.5, 2.5, 1.5.
        assert view_gen.x_coord_center == pytest.approx(2.5)
        assert view_gen.y_coord_center == pytest.approx(2.5)
        assert view_gen.z_coord_center == pytest.approx(1.5)

    def test_view_dimensions_match_bounding_box(self, view_gen):
        assert view_gen.view_horizontal == pytest.approx(5.0)
        assert view_gen.view_vertical == pytest.approx(5.0)

    def test_ffl_offset_clamped_when_non_positive(self, tmp_path):
        csv_path = tmp_path / "b.csv"
        _make_rb_csv(csv_path)
        vg = ViewGenerator(
            room_boundaries_csv_path=csv_path, ffl_offset=0,
            view_file_dir=tmp_path / "v", aoi_dir=tmp_path / "a",
        )
        assert vg.ffl_offset == 0.01

    def test_requires_exactly_one_source(self, tmp_path):
        with pytest.raises(SystemExit):
            ViewGenerator(
                room_boundaries_csv_path=None, aoi_inputs_dir=None,
                ffl_offset=1.0,
                view_file_dir=tmp_path / "v", aoi_dir=tmp_path / "a",
            )


class TestCreatePlanViewFiles:
    def test_writes_one_vp_per_unique_z(self, view_gen):
        assert view_gen.create_plan_view_files() is True
        vps = list(view_gen.view_file_dir.glob("*.vp"))
        # Two distinct Z levels in the fixture → 2 view files.
        assert len(vps) == 2

    def test_view_file_content_has_rvu_header(self, view_gen):
        view_gen.create_plan_view_files()
        vp = next(view_gen.view_file_dir.glob("*.vp"))
        text = vp.read_text()
        assert text.startswith("rvu")
        assert "-vp" in text
        assert "-vh" in text


class TestCreateAoiFiles:
    def test_writes_one_aoi_per_room(self, view_gen):
        assert view_gen.create_aoi_files() is True
        aois = list(view_gen.aoi_dir.glob("*.aoi"))
        # 2 rooms (BED + LIVING) → 2 files.
        assert len(aois) == 2

    def test_aoi_contents_have_expected_headers(self, view_gen):
        view_gen.create_aoi_files()
        aoi = next(view_gen.aoi_dir.glob("*.aoi"))
        text = aoi.read_text()
        assert "AOI Points File:" in text
        assert "ASSOCIATED VIEW FILE:" in text
        assert "FFL z height(m):" in text


class TestReadAoiFile:
    def test_parses_v2_format(self, tmp_path):
        aoi = tmp_path / "BED1.aoi"
        _make_v2_aoi(aoi, 3.0, [(0, 0), (1, 0), (1, 1), (0, 1)])
        name, z, verts = ViewGenerator._ViewGenerator__read_aoi_file(aoi)
        assert name == "BED1"
        assert z == 3.0
        assert verts == [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]

    def test_raises_when_no_points_header(self, tmp_path):
        bad = tmp_path / "bad.aoi"
        bad.write_text("FFL z height(m): 3.0\n")
        with pytest.raises(ValueError, match="POINTS"):
            ViewGenerator._ViewGenerator__read_aoi_file(bad)

    def test_raises_when_no_ffl(self, tmp_path):
        bad = tmp_path / "bad.aoi"
        bad.write_text("POINTS 2:\n0 0\n1 1\n")
        with pytest.raises(ValueError, match="FFL"):
            ViewGenerator._ViewGenerator__read_aoi_file(bad)


class TestParseAoiInputsDir:
    def test_builds_processed_csv_from_aoi_inputs(self, tmp_path):
        aoi_in = tmp_path / "aoi_in"
        aoi_in.mkdir()
        _make_v2_aoi(aoi_in / "r1.aoi", 3.0, [(0, 0), (1, 0), (1, 1)])
        _make_v2_aoi(aoi_in / "r2.aoi", 6.0, [(0, 0), (2, 0), (2, 2)])

        vg = ViewGenerator(
            aoi_inputs_dir=aoi_in,
            ffl_offset=1.0,
            view_file_dir=tmp_path / "v", aoi_dir=tmp_path / "a",
        )
        assert vg.processed_room_boundaries_csv_path.exists()
        df = pd.read_csv(vg.processed_room_boundaries_csv_path)
        # 3 + 3 = 6 vertex rows.
        assert len(df) == 6
        assert set(df["z_coords"].unique()) == {3.0, 6.0}
