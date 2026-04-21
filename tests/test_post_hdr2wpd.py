"""Tests for :mod:`archilume.post.hdr2wpd` — HDR → WPD extraction.

Covers the core logic of ``Hdr2Wpd`` and ``ViewGroupProcessor`` without
invoking real Radiance binaries. Pure-numpy DF computation is tested with
synthetic arrays; HDR loading is mocked where needed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from archilume import utils as arch_utils
from archilume.post import hdr2wpd as hw


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def pixel_map(tmp_path) -> arch_utils.PixelToWorldMap:
    # 10m × 10m world @ 100×100 px → area_per_pixel_m2 = 0.01.
    return arch_utils.PixelToWorldMap(
        hdr_path=tmp_path / "source.hdr",
        image_width=100, image_height=100,
        world_width_m=10.0, world_height_m=10.0,
        vp_x=0.0, vp_y=0.0,
    )


@pytest.fixture
def wpd_instance(tmp_path, pixel_map) -> hw.Hdr2Wpd:
    (tmp_path / "aoi").mkdir()
    (tmp_path / "image").mkdir()
    return hw.Hdr2Wpd(
        pixel_to_world_map=pixel_map,
        aoi_dir=tmp_path / "aoi",
        wpd_dir=tmp_path / "wpd",
        image_dir=tmp_path / "image",
    )


def _make_aoi(path: Path, view_name: str, pixels: list[tuple[int, int]]) -> None:
    """Write a minimal AOI file matching the 5-header-line format."""
    lines = [
        f"AOI Points File: {path.stem}",
        f"ASSOCIATED VIEW FILE: {view_name}.vp",
        "FFL z height(m): 0.85",
        "resolution: 100 100",
        "points:",
    ]
    for i, (x, y) in enumerate(pixels):
        # Columns: tag idx px py
        lines.append(f"v {i} {x} {y}")
    path.write_text("\n".join(lines) + "\n")


# =========================================================================
# Hdr2Wpd.__post_init__ + _calculate_area_per_pixel
# =========================================================================


class TestHdr2WpdInit:
    def test_post_init_creates_wpd_dir(self, tmp_path, pixel_map):
        wpd = tmp_path / "wpd"
        assert not wpd.exists()
        (tmp_path / "aoi").mkdir()
        (tmp_path / "image").mkdir()
        hw.Hdr2Wpd(
            pixel_to_world_map=pixel_map,
            aoi_dir=tmp_path / "aoi",
            wpd_dir=wpd,
            image_dir=tmp_path / "image",
        )
        assert wpd.exists()

    def test_area_per_pixel_derived_from_map(self, wpd_instance):
        assert wpd_instance.area_per_pixel == pytest.approx(0.01)
        assert wpd_instance.pixel_increment_x == pytest.approx(0.1)
        assert wpd_instance.pixel_increment_y == pytest.approx(0.1)


# =========================================================================
# compute_df_for_polygon
# =========================================================================


class TestComputeDfForPolygon:
    def test_uniform_df_over_threshold(self, wpd_instance):
        # 50×50 image at 2.5% DF, 10×10 polygon centred.
        img = np.full((50, 50), 2.5, dtype=np.float32)
        verts = [[20, 20], [30, 20], [30, 30], [20, 30]]
        out = wpd_instance.compute_df_for_polygon(
            img, verts, df_thresholds=(0.5, 1.0, 2.0),
        )
        assert out["total_pixels"] > 0
        # All pixels exceed all thresholds.
        for entry in out["thresholds"]:
            assert entry["passing_pixels"] == out["total_pixels"]

    def test_empty_polygon_returns_zero_thresholds(self, wpd_instance):
        img = np.zeros((20, 20), dtype=np.float32)
        out = wpd_instance.compute_df_for_polygon(
            img, [[-5, -5], [-3, -5], [-5, -3]],
        )
        assert out["total_pixels"] == 0
        assert all(t["passing_pixels"] == 0 for t in out["thresholds"])

    def test_area_m2_scales_with_area_per_pixel(self, wpd_instance):
        # area_per_pixel = 0.01 m²; polygon with ~100 pixels → ~1 m².
        img = np.full((50, 50), 3.0, dtype=np.float32)
        verts = [[0, 0], [10, 0], [10, 10], [0, 10]]
        out = wpd_instance.compute_df_for_polygon(img, verts, df_thresholds=(1.0,))
        assert out["total_area_m2"] == pytest.approx(
            out["total_pixels"] * 0.01, rel=1e-6,
        )


# =========================================================================
# compute_df_for_polygon_excluding
# =========================================================================


class TestComputeDfExcluding:
    def test_subtracts_child_pixels(self, wpd_instance):
        img = np.full((50, 50), 2.5, dtype=np.float32)
        parent = [[10, 10], [40, 10], [40, 40], [10, 40]]
        child = [[20, 20], [30, 20], [30, 30], [20, 30]]

        full = wpd_instance.compute_df_for_polygon(img, parent)
        minus = wpd_instance.compute_df_for_polygon_excluding(img, parent, [child])
        assert minus["total_pixels"] < full["total_pixels"]

    def test_ignores_degenerate_children(self, wpd_instance):
        img = np.full((20, 20), 1.0, dtype=np.float32)
        parent = [[0, 0], [10, 0], [10, 10], [0, 10]]
        bad_child = [[5, 5], [5, 5]]  # <3 verts

        a = wpd_instance.compute_df_for_polygon(img, parent)
        b = wpd_instance.compute_df_for_polygon_excluding(img, parent, [bad_child])
        assert b["total_pixels"] == a["total_pixels"]

    def test_fully_contained_child_returns_zero(self, wpd_instance):
        img = np.ones((20, 20), dtype=np.float32)
        poly = [[0, 0], [10, 0], [10, 10], [0, 10]]
        out = wpd_instance.compute_df_for_polygon_excluding(img, poly, [poly])
        assert out["total_pixels"] == 0


# =========================================================================
# _scan_directories
# =========================================================================


class TestScanDirectories:
    def test_finds_hdrs_and_aois(self, wpd_instance):
        (wpd_instance.image_dir / "a.hdr").write_text("")
        (wpd_instance.image_dir / "b.hdr").write_text("")
        (wpd_instance.aoi_dir / "room.aoi").write_text("")
        hdrs, aois = wpd_instance._scan_directories()
        assert len(hdrs) == 2
        assert len(aois) == 1

    def test_empty_dirs_return_empty_lists(self, wpd_instance):
        hdrs, aois = wpd_instance._scan_directories()
        assert hdrs == [] and aois == []


# =========================================================================
# _group_aoi_by_view
# =========================================================================


class TestGroupAoiByView:
    def test_groups_aois_and_matches_hdrs(self, wpd_instance):
        aoi = wpd_instance.aoi_dir / "room1.aoi"
        _make_aoi(aoi, "plan_ffl_090000", [(10, 10), (20, 10), (15, 20)])
        hdr = wpd_instance.image_dir / "plan_ffl_090000_SS_0900.hdr"
        hdr.write_text("")

        groups = wpd_instance._group_aoi_by_view([aoi], [hdr])
        assert "plan_ffl_090000" in groups
        assert hdr in groups["plan_ffl_090000"]["hdr_files"]
        assert aoi in groups["plan_ffl_090000"]["aoi_files"]

    def test_skips_aois_with_existing_wpd(self, wpd_instance):
        aoi = wpd_instance.aoi_dir / "done.aoi"
        _make_aoi(aoi, "plan_ffl_090000", [(0, 0), (1, 0), (1, 1)])
        # Pre-create the wpd so the AOI is skipped.
        wpd_instance.wpd_dir.mkdir(exist_ok=True)
        (wpd_instance.wpd_dir / "done.wpd").write_text("x")

        groups = wpd_instance._group_aoi_by_view([aoi], [])
        assert groups == {}  # Nothing to process

    def test_warns_on_aois_missing_view_ref(self, wpd_instance, capsys):
        aoi = wpd_instance.aoi_dir / "bad.aoi"
        aoi.write_text("no view line here\n")
        groups = wpd_instance._group_aoi_by_view([aoi], [])
        out = capsys.readouterr().out
        assert "Could not extract view file" in out
        assert groups == {}


# =========================================================================
# load_df_image (static)
# =========================================================================


class TestLoadDfImage:
    def test_returns_none_on_pvalue_failure(self, tmp_path, monkeypatch, capsys):
        hdr = tmp_path / "a.hdr"
        hdr.write_text("")
        # get_hdr_resolution raising → load_df_image returns None.
        monkeypatch.setattr(
            arch_utils, "get_hdr_resolution",
            lambda p: (_ for _ in ()).throw(RuntimeError("no pvalue")),
        )
        assert hw.Hdr2Wpd.load_df_image(hdr) is None

    def test_returns_scaled_df_array(self, tmp_path, monkeypatch):
        hdr = tmp_path / "a.hdr"
        hdr.write_bytes(b"")
        width, height = 4, 4
        monkeypatch.setattr(arch_utils, "get_hdr_resolution",
                            lambda p: (width, height))

        class _R:
            stdout = np.full((height, width), 1.0, dtype=np.float32).tobytes()

        import subprocess as _sp
        monkeypatch.setattr(_sp, "run", lambda *a, **kw: _R())
        monkeypatch.setattr(hw.subprocess, "run", lambda *a, **kw: _R())

        img = hw.Hdr2Wpd.load_df_image(hdr)
        assert img is not None
        assert img.shape == (height, width)
        # Scaled by 1.79 (W/m² → DF%).
        assert img[0, 0] == pytest.approx(1.79)


# =========================================================================
# ViewGroupProcessor.__post_init__ + _write_wpd_files
# =========================================================================


class TestViewGroupProcessor:
    def test_post_init_empty_inputs_noop(self, tmp_path):
        proc = hw.ViewGroupProcessor(
            view_name="v",
            aoi_files=[], hdr_files=[],
            pixel_threshold_value=1.0,
            wpd_output_dir=tmp_path,
        )
        # No masks or counts without inputs.
        assert proc._aoi_masks == {}

    def test_post_init_builds_masks(self, tmp_path, monkeypatch):
        hdr = tmp_path / "a.hdr"
        hdr.write_text("")
        aoi = tmp_path / "r.aoi"
        _make_aoi(aoi, "view", [(5, 5), (20, 5), (20, 20), (5, 20)])

        monkeypatch.setattr(arch_utils, "get_hdr_resolution", lambda p: (50, 50))

        proc = hw.ViewGroupProcessor(
            view_name="v",
            aoi_files=[aoi], hdr_files=[hdr],
            pixel_threshold_value=1.0,
            wpd_output_dir=tmp_path,
        )
        assert aoi in proc._aoi_masks
        mask = proc._aoi_masks[aoi]
        assert mask.shape == (50, 50)
        assert mask.dtype == bool
        assert mask.sum() > 0
        assert proc._aoi_pixel_counts[aoi] > 0

    def test_write_wpd_files_produces_output(self, tmp_path, monkeypatch):
        hdr = tmp_path / "a.hdr"
        hdr.write_text("")
        aoi = tmp_path / "room.aoi"
        _make_aoi(aoi, "v", [(5, 5), (20, 5), (20, 20)])

        monkeypatch.setattr(arch_utils, "get_hdr_resolution", lambda p: (50, 50))

        proc = hw.ViewGroupProcessor(
            view_name="v",
            aoi_files=[aoi], hdr_files=[hdr],
            pixel_threshold_value=1.0,
            wpd_output_dir=tmp_path,
        )
        # Stage fake per-HDR results.
        aoi_results = {
            aoi: [{"hdr_file": "h1.hdr", "passing_pixels": 30},
                  {"hdr_file": "h2.hdr", "passing_pixels": 42}],
        }
        proc._write_wpd_files(aoi_results)
        wpd = tmp_path / "room.wpd"
        assert wpd.exists()
        content = wpd.read_text()
        assert "total_pixels_in_polygon" in content
        assert "h1.hdr" in content
        assert "h2.hdr" in content
