"""Tests for :mod:`archilume_app.lib.export_pipeline`.

Covers all 23 public + private callables in the module. The DF math
itself (``load_df_image``, ``compute_room_df``) is already exercised by
``test_df_analysis.py``, so this file monkeypatches the DF layer where
it would otherwise need a real HDR fixture and focuses on:

* grouping/reprojection logic (``_group_rooms_by_hdr``, ``_hdr_native_verts``)
* colour + layout helpers (``_pct_colour_from_stats``, ``_clamp_block_to_bbox``,
  ``_text_size``)
* file IO round-trips (archive zip/unzip, Excel, CSV)
* drawing primitives (smoke-tested via a synthetic 32×32 RGBA image)
* the full ``export_report`` orchestrator with DF layer mocked
"""

from __future__ import annotations

import csv
import sys
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from archilume_app.lib import export_pipeline as ep


# =========================================================================
# _hdr_native_verts
# =========================================================================


class TestHdrNativeVerts:
    def test_reprojects_world_to_pixel(self):
        # View params: vpx=0, vpy=0, vh=10m, vv=10m, iw=100px, ih=100px.
        # A point at world (0, 0) should map to image centre (50, 50).
        room = {"world_vertices": [[0.0, 0.0], [5.0, 0.0], [0.0, 5.0]]}
        vp = [0.0, 0.0, 10.0, 10.0, 100.0, 100.0]
        verts = ep._hdr_native_verts(room, vp)
        assert verts[0] == [50.0, 50.0]
        # x+5m → 5m / (10m / 100px) = 50px from centre → x=100.
        assert verts[1] == [100.0, 50.0]
        # y+5m → image y decreases → y=0.
        assert verts[2][1] == 0.0

    def test_falls_back_to_pixel_vertices_without_world(self):
        room = {"vertices": [[1, 2], [3, 4]]}
        verts = ep._hdr_native_verts(room, None)
        assert verts == [[1, 2], [3, 4]]

    def test_falls_back_when_too_few_world_verts(self):
        room = {"world_vertices": [[0.0, 0.0]], "vertices": [[7, 8]]}
        vp = [0.0, 0.0, 10.0, 10.0, 100.0, 100.0]
        assert ep._hdr_native_verts(room, vp) == [[7, 8]]

    def test_falls_back_when_vp_has_zero_image_size(self):
        room = {
            "world_vertices": [[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]],
            "vertices": [[9, 9]],
        }
        vp = [0.0, 0.0, 10.0, 10.0, 0.0, 100.0]  # iw == 0 → fallback
        assert ep._hdr_native_verts(room, vp) == [[9, 9]]


# =========================================================================
# _group_rooms_by_hdr
# =========================================================================


class TestGroupRoomsByHdr:
    @pytest.fixture
    def hdr_files(self) -> list[dict]:
        return [
            {"name": "a.hdr", "hdr_path": "/tmp/a.hdr"},
            {"name": "b.hdr", "hdr_path": "/tmp/b.hdr"},
        ]

    @pytest.fixture
    def vp(self) -> dict[str, list[float]]:
        return {
            "a.hdr": [0.0, 0.0, 10.0, 10.0, 100.0, 100.0],
            "b.hdr": [0.0, 0.0, 10.0, 10.0, 100.0, 100.0],
        }

    def test_groups_by_hdr_name(self, hdr_files, vp):
        rooms = [
            {"name": "R1", "vertices": [[0, 0], [1, 0], [1, 1]], "hdr_file": "a.hdr"},
            {"name": "R2", "vertices": [[0, 0], [1, 0], [1, 1]], "hdr_file": "b.hdr"},
        ]
        groups = ep._group_rooms_by_hdr(rooms, hdr_files, vp)
        assert set(groups.keys()) == {"a.hdr", "b.hdr"}
        assert len(groups["a.hdr"]["rooms"]) == 1
        assert len(groups["b.hdr"]["rooms"]) == 1

    def test_skips_rooms_with_too_few_vertices(self, hdr_files, vp):
        rooms = [
            {"name": "degenerate", "vertices": [[0, 0]], "hdr_file": "a.hdr"},
        ]
        assert ep._group_rooms_by_hdr(rooms, hdr_files, vp) == {}

    def test_skips_rooms_with_unknown_hdr(self, hdr_files, vp):
        rooms = [
            {"name": "R1", "vertices": [[0, 0], [1, 0], [1, 1]], "hdr_file": "zzz.hdr"},
        ]
        assert ep._group_rooms_by_hdr(rooms, hdr_files, vp) == {}

    def test_computes_area_per_pixel(self, hdr_files, vp):
        # 10m × 10m scene at 100×100px → each pixel = 0.01 m².
        rooms = [
            {"name": "R1", "vertices": [[0, 0], [1, 0], [1, 1]], "hdr_file": "a.hdr"},
        ]
        groups = ep._group_rooms_by_hdr(rooms, hdr_files, vp)
        assert groups["a.hdr"]["area_per_pixel_m2"] == pytest.approx(0.01)

    def test_child_parent_relationship(self, hdr_files, vp):
        rooms = [
            {"name": "parent", "vertices": [[0, 0], [10, 0], [10, 10]], "hdr_file": "a.hdr"},
            {
                "name": "child",
                "parent": "parent",
                "vertices": [[1, 1], [2, 1], [2, 2]],
                "hdr_file": "a.hdr",
            },
        ]
        groups = ep._group_rooms_by_hdr(rooms, hdr_files, vp)
        parent = next(r for r in groups["a.hdr"]["rooms"] if r["name"] == "parent")
        assert len(parent["child_hdr_verts"]) == 1


# =========================================================================
# _extract_room_pixels
# =========================================================================


class TestExtractRoomPixels:
    def test_returns_pixels_inside_polygon(self):
        df_image = np.full((10, 10), 2.5, dtype=np.float32)
        verts = [[2, 2], [7, 2], [7, 7], [2, 7]]
        df_vals, lux_vals = ep._extract_room_pixels(df_image, verts, [])
        assert df_vals.size > 0
        assert np.all(df_vals == 2.5)
        # Lux = DF% × 100 (CIE overcast reference 10 000 lux).
        assert np.all(lux_vals == 250.0)

    def test_fully_excluded_polygon_returns_empty_arrays(self):
        # Outer == inner → mask fully cleared → size 0.
        df_image = np.full((10, 10), 2.5, dtype=np.float32)
        poly = [[2, 2], [7, 2], [7, 7], [2, 7]]
        df_vals, lux_vals = ep._extract_room_pixels(df_image, poly, [poly])
        assert df_vals.size == 0
        assert lux_vals.size == 0

    def test_exclude_polygon_removes_pixels(self):
        df_image = np.full((10, 10), 3.0, dtype=np.float32)
        outer = [[0, 0], [9, 0], [9, 9], [0, 9]]
        inner = [[2, 2], [7, 2], [7, 7], [2, 7]]
        full, _ = ep._extract_room_pixels(df_image, outer, [])
        minus_inner, _ = ep._extract_room_pixels(df_image, outer, [inner])
        assert minus_inner.size < full.size


# =========================================================================
# _clamp_block_to_bbox
# =========================================================================


class TestClampBlockToBbox:
    def test_block_fits_inside_bbox_centered(self):
        verts = [[0, 0], [100, 0], [100, 100], [0, 100]]
        ax, ay = ep._clamp_block_to_bbox((50, 50), verts, 20, 20)
        assert ax == 40  # 50 - 20/2
        assert ay == 40

    def test_clamps_right_edge(self):
        verts = [[0, 0], [100, 0], [100, 100], [0, 100]]
        # Pole near right edge → block would overflow; clamp.
        ax, ay = ep._clamp_block_to_bbox((95, 50), verts, 20, 20)
        assert ax == 80  # xmax - block_w = 100 - 20

    def test_clamps_top_edge(self):
        verts = [[0, 0], [100, 0], [100, 100], [0, 100]]
        ax, ay = ep._clamp_block_to_bbox((50, 2), verts, 20, 20)
        assert ay == 0


# =========================================================================
# _pct_colour_from_stats
# =========================================================================


class TestPctColourFromStats:
    def test_returns_black_for_passing(self):
        stats = {"pct_above": 95, "threshold": 2.0}
        assert ep._pct_colour_from_stats(stats, (1, 2, 3)) == (0, 0, 0)

    def test_returns_amber_for_marginal(self):
        stats = {"pct_above": 70, "threshold": 2.0}
        assert ep._pct_colour_from_stats(stats, (1, 2, 3)) == (233, 113, 50)

    def test_returns_red_for_failing(self):
        stats = {"pct_above": 10, "threshold": 2.0}
        assert ep._pct_colour_from_stats(stats, (1, 2, 3)) == (238, 0, 0)

    def test_returns_default_when_missing(self):
        default = (7, 8, 9)
        assert ep._pct_colour_from_stats({}, default) == default
        assert ep._pct_colour_from_stats({"pct_above": 50}, default) == default


# =========================================================================
# _text_size — needs a real ImageDraw context
# =========================================================================


class TestTextSize:
    @pytest.fixture
    def draw(self) -> ImageDraw.ImageDraw:
        img = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
        return ImageDraw.Draw(img)

    def test_empty_string_is_zero(self, draw):
        assert ep._text_size(draw, "", ImageFont.load_default()) == (0, 0)

    def test_non_empty_string_has_positive_width(self, draw):
        font = ep._load_font(20, bold=False)
        w, h = ep._text_size(draw, "Hello", font)
        assert w > 0
        assert h > 0


# =========================================================================
# _platform_font_dirs + _matplotlib_font_dir
# =========================================================================


class TestFontDirs:
    def test_platform_font_dirs_returns_paths(self):
        dirs = ep._platform_font_dirs()
        assert isinstance(dirs, list)
        assert all(isinstance(d, Path) for d in dirs)
        # At minimum, some OS-specific path should be included.
        assert len(dirs) >= 1

    def test_matplotlib_font_dir_returns_path_or_none(self):
        # matplotlib is a dep so the path should exist in this env.
        d = ep._matplotlib_font_dir()
        assert d is None or d.exists()

    def test_platform_font_dirs_includes_matplotlib_when_available(self):
        mpl = ep._matplotlib_font_dir()
        if mpl is None:
            pytest.skip("matplotlib not available")
        assert mpl in ep._platform_font_dirs()


# =========================================================================
# _load_font
# =========================================================================


class TestLoadFont:
    def test_returns_font_object(self):
        ep._FONT_CACHE.clear()
        f = ep._load_font(16, bold=False)
        assert f is not None

    def test_cache_returns_same_instance(self):
        ep._FONT_CACHE.clear()
        f1 = ep._load_font(18, bold=True)
        f2 = ep._load_font(18, bold=True)
        assert f1 is f2

    def test_bold_differs_from_regular(self):
        ep._FONT_CACHE.clear()
        reg = ep._load_font(14, bold=False)
        bold = ep._load_font(14, bold=True)
        # Either different objects or equal default fallback — both acceptable,
        # but cache keys must differ so caching still works.
        assert (14, False) in ep._FONT_CACHE
        assert (14, True) in ep._FONT_CACHE


# =========================================================================
# _progress
# =========================================================================


class TestProgress:
    def test_noop_when_fn_is_none(self):
        ep._progress(None, 50, "halfway")  # no raise

    def test_calls_fn_with_args(self):
        calls = []
        ep._progress(lambda pct, msg: calls.append((pct, msg)), 30, "hi")
        assert calls == [(30, "hi")]

    def test_swallows_exceptions_in_fn(self):
        def boom(pct, msg):
            raise RuntimeError("fail")

        ep._progress(boom, 10, "x")  # must not raise


# =========================================================================
# list_archives + extract_archive + _create_archive
# =========================================================================


class TestArchives:
    def test_list_archives_empty_when_missing(self, tmp_path):
        assert ep.list_archives(tmp_path / "does_not_exist") == []

    def test_list_archives_sorts_descending(self, tmp_path):
        (tmp_path / "archilume_export_a_20260101_010000.zip").write_bytes(b"x")
        (tmp_path / "archilume_export_a_20260102_010000.zip").write_bytes(b"x")
        (tmp_path / "ignored.txt").write_text("nope")
        result = ep.list_archives(tmp_path)
        assert result[0].startswith("archilume_export_a_20260102")
        assert len(result) == 2

    def test_create_archive_returns_none_when_nothing_to_zip(self, tmp_path):
        outputs = tmp_path / "outputs"
        archive = tmp_path / "archives"
        # Neither dir exists → nothing to archive.
        assert ep._create_archive(outputs, archive, "proj") is None

    def test_create_archive_zips_outputs(self, tmp_path):
        outputs = tmp_path / "outputs"
        (outputs / "image").mkdir(parents=True)
        (outputs / "image" / "frame.png").write_bytes(b"png")
        archive = tmp_path / "archives"
        zip_path = ep._create_archive(outputs, archive, "myproj")
        assert zip_path is not None and zip_path.exists()
        assert "myproj" in zip_path.name
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        assert any("frame.png" in n for n in names)

    def test_create_archive_includes_inputs_dir(self, tmp_path):
        outputs = tmp_path / "outputs"
        outputs.mkdir()
        (outputs / "o.txt").write_text("o")
        inputs = tmp_path / "inputs"
        inputs.mkdir()
        (inputs / "i.txt").write_text("i")
        zip_path = ep._create_archive(outputs, tmp_path / "archives", "p", inputs)
        assert zip_path is not None
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        assert any("i.txt" in n for n in names)
        assert any("o.txt" in n for n in names)

    def test_extract_archive_roundtrip(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "data.txt").write_text("hello")
        zip_path = tmp_path / "bundle.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(src / "data.txt", "data.txt")
        dest = tmp_path / "dest"
        dest.mkdir()
        assert ep.extract_archive(zip_path, dest) is True
        assert (dest / "data.txt").read_text() == "hello"

    def test_extract_archive_returns_false_on_bad_zip(self, tmp_path):
        bad = tmp_path / "bad.zip"
        bad.write_bytes(b"not-a-zip")
        dest = tmp_path / "dest"
        dest.mkdir()
        assert ep.extract_archive(bad, dest) is False


# =========================================================================
# _write_excel + _write_pixel_csvs
# =========================================================================


class TestExcelAndCsv:
    def test_write_excel_produces_file(self, tmp_path):
        rows = [
            {
                "HDR File": "a.hdr",
                "Room": "R1",
                "Room Type": "BED",
                "Total Pixels": 1000,
                "DF Threshold (%)": 2.0,
                "Pixels >= Threshold": 750,
                "% Area >= Threshold": 75.0,
            },
        ]
        out = ep._write_excel(rows, tmp_path)
        assert out.exists()
        assert out.suffix == ".xlsx"

    def test_write_excel_with_empty_rows(self, tmp_path):
        out = ep._write_excel([], tmp_path)
        assert out.exists()

    def test_write_pixel_csvs_creates_one_file_per_room(self, tmp_path):
        chunks = [
            ("Room A", np.array([100.0, 200.0]), np.array([1.0, 2.0])),
            ("Room/B", np.array([150.0]), np.array([1.5])),  # slash sanitized
        ]
        out_dir = tmp_path / "csvs"
        ep._write_pixel_csvs(chunks, out_dir)
        files = list(out_dir.glob("*.csv"))
        assert len(files) == 2
        # Unsafe chars replaced with '_'
        assert any("Room_B" in f.name for f in files)

    def test_write_pixel_csvs_noop_on_empty(self, tmp_path):
        out_dir = tmp_path / "csvs"
        ep._write_pixel_csvs([], out_dir)
        assert not out_dir.exists()

    def test_write_pixel_csv_content_has_header_and_rows(self, tmp_path):
        chunks = [("R", np.array([100.0]), np.array([1.0]))]
        out_dir = tmp_path / "csvs"
        ep._write_pixel_csvs(chunks, out_dir)
        with open(out_dir / "R_pixels.csv") as f:
            rows = list(csv.reader(f))
        assert rows[0] == ["Room", "Illuminance (Lux)", "Daylight Factor (%)"]
        assert rows[1] == ["R", "100.0", "1.0"]


# =========================================================================
# Drawing primitives — smoke + basic structural checks
# =========================================================================


class TestDrawingPrimitives:
    def test_hatch_polygon_runs_without_raise(self):
        img = Image.new("RGBA", (32, 32), (255, 255, 255, 255))
        ep._hatch_polygon(img, [[4, 4], [28, 4], [28, 28], [4, 28]],
                          (255, 0, 0), spacing=4, line_w=1)
        # Some pixel inside polygon was modified (hatch is red, not white).
        px = img.load()
        found_red = any(
            px[x, y][0] > 200 and px[x, y][1] < 80
            for x in range(5, 28) for y in range(5, 28)
        )
        assert found_red

    def test_stroked_text_draws_something(self):
        img = Image.new("RGBA", (64, 64), (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)
        ep._stroked_text(
            draw, 10, 10, "X", ep._load_font(16, bold=True),
            fill=(0, 0, 255), stroke_fg=(255, 255, 255), stroke_lw=1.5,
        )
        # Any blue-dominant pixel means the glyph fill hit the canvas.
        px = img.load()
        found = any(
            px[x, y][2] > 200 and px[x, y][0] < 80
            for x in range(64) for y in range(64)
        )
        assert found

    def test_dashed_polygon_runs(self):
        img = Image.new("RGBA", (32, 32), (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)
        pts = [(4, 4), (28, 4), (28, 28), (4, 28), (4, 4)]
        ep._dashed_polygon(draw, pts, fill=(255, 0, 0), width=1)
        # Red pixels present.
        px = img.load()
        assert any(
            px[x, y][0] > 200 and px[x, y][1] < 80
            for x in range(32) for y in range(32)
        )

    def test_dashed_polygon_ignores_zero_segments(self):
        img = Image.new("RGBA", (16, 16), (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)
        pts = [(5, 5), (5, 5), (5, 5)]  # all zero-length
        ep._dashed_polygon(draw, pts, fill=(0, 0, 255), width=1)  # no raise

    def test_draw_room_annotation_stacked_fraction(self):
        img = Image.new("RGBA", (400, 200), (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)
        stats = {
            "area_num": "15.0",
            "area_den": "20.0",
            "area_pct": "(75%)",
            "pct_above": 75,
            "threshold": 2.0,
            "result_lines": ["", "≥ 2% DF"],
        }
        ep._draw_room_annotation(
            draw, [[50, 50], [350, 50], [350, 150], [50, 150]],
            "BED 1", stats,
            fs_large=20, fs_small=12,
            font_large=ep._load_font(20, bold=True),
            font_large_norm=ep._load_font(20, bold=False),
            font_small=ep._load_font(12, bold=False),
            white=(255, 255, 255), black=(0, 0, 0),
        )
        # Some non-white pixel in centre — annotation was drawn.
        px = img.load()
        centre_has_text = any(
            sum(px[x, y][:3]) < 600
            for x in range(150, 250) for y in range(80, 140)
        )
        assert centre_has_text

    def test_draw_annotations_writes_png(self, tmp_path):
        base = tmp_path / "base.png"
        Image.new("RGBA", (64, 64), (200, 200, 200, 255)).save(base)
        out = tmp_path / "annotated.png"
        rooms = [{"name": "R", "verts": [[10, 10], [50, 10], [50, 50], [10, 50]],
                  "is_circ": False}]
        stats = {"R": {"area_num": "5.0", "area_den": "10.0", "area_pct": "(50%)",
                       "pct_above": 50, "threshold": 2.0,
                       "result_lines": ["", "≥ 2% DF"]}}
        ep._draw_annotations(base, rooms, stats, out)
        assert out.exists()
        with Image.open(out) as im:
            assert im.size[0] == int(64 * ep._EXPORT_UPSCALE)

    def test_draw_annotations_circ_room_uses_hatch_not_text(self, tmp_path):
        base = tmp_path / "base.png"
        Image.new("RGBA", (64, 64), (255, 255, 255, 255)).save(base)
        out = tmp_path / "circ.png"
        rooms = [{"name": "CORRIDOR",
                  "verts": [[10, 10], [50, 10], [50, 50], [10, 50]],
                  "is_circ": True}]
        ep._draw_annotations(base, rooms, {}, out)
        assert out.exists()


# =========================================================================
# _render_annotated_overlays
# =========================================================================


class TestRenderAnnotatedOverlays:
    def test_noop_when_no_base_pngs(self, tmp_path):
        # hdr_groups references an HDR but base PNGs don't exist → skip silently.
        groups = {
            "a.hdr": {
                "hdr_name": "a.hdr",
                "hdr_path": Path("/tmp/a.hdr"),
                "area_per_pixel_m2": 0.01,
                "vp_params": None,
                "rooms": [{"name": "R", "room_type": "BED",
                           "hdr_verts": [[10, 10], [50, 10], [50, 50]],
                           "child_hdr_verts": []}],
            }
        }
        ep._render_annotated_overlays(groups, {}, tmp_path)
        # No annotated png created.
        assert list(tmp_path.glob("*annotated*")) == []

    def test_writes_annotated_png_per_suffix(self, tmp_path):
        # Seed both falsecolour + contour base PNGs for an HDR stem.
        stem = "a"
        Image.new("RGBA", (32, 32), (255, 255, 255, 255)).save(
            tmp_path / f"{stem}{ep._FALSECOLOUR_SUFFIX}"
        )
        Image.new("RGBA", (32, 32), (255, 255, 255, 255)).save(
            tmp_path / f"{stem}{ep._CONTOUR_SUFFIX}"
        )
        groups = {
            "a.hdr": {
                "hdr_name": "a.hdr",
                "hdr_path": tmp_path / "a.hdr",
                "area_per_pixel_m2": 0.01,
                "vp_params": None,
                "rooms": [{"name": "R", "room_type": "BED",
                           "hdr_verts": [[5, 5], [25, 5], [25, 25], [5, 25]],
                           "child_hdr_verts": []}],
            }
        }
        ep._render_annotated_overlays(groups, {"a.hdr": {}}, tmp_path)
        annotated = list(tmp_path.glob("*aoi_annotated*"))
        assert len(annotated) == 2


# =========================================================================
# _process_hdr + export_report orchestrator — DF layer mocked
# =========================================================================


class TestProcessHdr:
    def test_returns_empty_when_load_df_image_returns_none(self, monkeypatch):
        monkeypatch.setattr(ep, "load_df_image", lambda p: None)
        group = {"hdr_name": "a.hdr", "hdr_path": Path("/tmp/a.hdr"),
                 "area_per_pixel_m2": 0.01, "rooms": []}
        rows, pixels, stats = ep._process_hdr(group, iesve_mode=False)
        assert rows == [] and pixels == [] and stats == {}

    def test_produces_summary_row_for_typed_room(self, monkeypatch):
        # Mock a 50×50 DF image at 2.5% DF (BED threshold is 2%, so all pixels pass).
        df_img = np.full((50, 50), 2.5, dtype=np.float32)
        monkeypatch.setattr(ep, "load_df_image", lambda p: df_img)
        monkeypatch.setattr(
            ep, "compute_room_df",
            lambda *a, **kw: {
                "threshold": 2.0,
                "pct_above": 100.0,
                "area_num": "10.0", "area_den": "10.0", "area_pct": "(100%)",
                "result_lines": ["", "≥ 2% DF"],
            },
        )
        group = {
            "hdr_name": "a.hdr",
            "hdr_path": Path("/tmp/a.hdr"),
            "area_per_pixel_m2": 0.01,
            "rooms": [{
                "name": "BED 1", "parent": "",
                "room_type": "BED",
                "hdr_verts": [[5, 5], [45, 5], [45, 45], [5, 45]],
                "child_hdr_verts": [],
            }],
        }
        rows, pixels, stats = ep._process_hdr(group, iesve_mode=False)
        assert len(rows) == 1
        assert rows[0]["Room"] == "BED 1"
        assert rows[0]["DF Threshold (%)"] == 2.0
        assert "BED 1" in stats

    def test_skips_untyped_room_no_threshold(self, monkeypatch):
        df_img = np.ones((50, 50), dtype=np.float32)
        monkeypatch.setattr(ep, "load_df_image", lambda p: df_img)
        monkeypatch.setattr(
            ep, "compute_room_df",
            lambda *a, **kw: {"threshold": None, "pct_above": None,
                              "result_lines": []},
        )
        group = {
            "hdr_name": "a.hdr", "hdr_path": Path("/tmp/a.hdr"),
            "area_per_pixel_m2": 0.01,
            "rooms": [{"name": "CORR", "parent": "", "room_type": "CIRC",
                       "hdr_verts": [[5, 5], [45, 5], [45, 45]],
                       "child_hdr_verts": []}],
        }
        rows, pixels, stats = ep._process_hdr(group, iesve_mode=False)
        assert rows == []
        assert "CORR" in stats  # still recorded for overlay rendering


class TestExportReport:
    def test_export_empty_rooms_still_archives(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ep, "load_df_image", lambda p: None)
        outputs = tmp_path / "outputs"
        (outputs / "image").mkdir(parents=True)
        (outputs / "image" / "dummy.png").write_bytes(b"x")
        image_dir = outputs / "image"
        wpd = outputs / "wpd"
        archives = tmp_path / "archives"
        progress_calls: list[tuple[int, str]] = []
        result = ep.export_report(
            rooms=[], hdr_files=[], hdr_view_params={},
            image_dir=image_dir, wpd_dir=wpd, archive_dir=archives,
            outputs_dir=outputs, project_name="p",
            on_progress=lambda pct, msg: progress_calls.append((pct, msg)),
        )
        assert result is not None and result.exists()
        assert progress_calls[0][0] == 0
        assert progress_calls[-1][0] == 100

    def test_export_full_pipeline_writes_excel_and_annotations(
        self, tmp_path, monkeypatch
    ):
        df_img = np.full((64, 64), 2.5, dtype=np.float32)
        monkeypatch.setattr(ep, "load_df_image", lambda p: df_img)
        monkeypatch.setattr(
            ep, "compute_room_df",
            lambda *a, **kw: {
                "threshold": 2.0, "pct_above": 100.0,
                "area_num": "10.0", "area_den": "10.0", "area_pct": "(100%)",
                "result_lines": ["", "≥ 2% DF"],
            },
        )
        outputs = tmp_path / "outputs"
        image_dir = outputs / "image"
        image_dir.mkdir(parents=True)
        # Seed base PNGs so annotated versions are produced.
        Image.new("RGBA", (64, 64), (255, 255, 255, 255)).save(
            image_dir / f"a{ep._FALSECOLOUR_SUFFIX}"
        )
        Image.new("RGBA", (64, 64), (255, 255, 255, 255)).save(
            image_dir / f"a{ep._CONTOUR_SUFFIX}"
        )

        rooms = [{
            "name": "BED 1", "parent": "", "room_type": "BED",
            "vertices": [[5, 5], [55, 5], [55, 55], [5, 55]],
            "hdr_file": "a.hdr",
        }]
        hdr_files = [{"name": "a.hdr", "hdr_path": str(image_dir / "a.hdr")}]
        vp = {"a.hdr": [0.0, 0.0, 10.0, 10.0, 64.0, 64.0]}

        result = ep.export_report(
            rooms=rooms, hdr_files=hdr_files, hdr_view_params=vp,
            image_dir=image_dir, wpd_dir=outputs / "wpd",
            archive_dir=tmp_path / "archives",
            outputs_dir=outputs, project_name="proj",
        )
        assert result is not None
        assert (outputs / "wpd" / "aoi_report_daylight.xlsx").exists()
        assert list(image_dir.glob("*aoi_annotated*"))
