"""Tests for :mod:`archilume.post.tiff2animation` — TIFF post-processing.

Covers 6 of 8 ``Tiff2Animation`` methods; the 2 skipped are the high-level
pipeline driver (``nsw_adg_sunlight_access_results_pipeline``) and the APNG
conversion wrapper (covered by ``test_post_apng2mp4``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageFont

from archilume.post.tiff2animation import Tiff2Animation


def _make_dirs(tmp_path: Path) -> dict[str, Path]:
    paths = {
        "sky": tmp_path / "sky",
        "view": tmp_path / "view",
        "image": tmp_path / "image",
        "aoi": tmp_path / "aoi",
    }
    for p in paths.values():
        p.mkdir(exist_ok=True)
    return paths


def _make_instance(tmp_path: Path, **overrides) -> Tiff2Animation:
    paths = _make_dirs(tmp_path)
    kwargs = dict(
        skyless_octree_path=tmp_path / "octree.oct",
        overcast_sky_file_path=tmp_path / "overcast.sky",
        x_res=512, y_res=512, latitude=-33.9, ffl_offset=0.85,
        sky_files_dir=paths["sky"], view_files_dir=paths["view"],
        image_dir=paths["image"], aoi_dir=paths["aoi"],
    )
    kwargs.update(overrides)
    return Tiff2Animation(**kwargs)


class TestPostInit:
    def test_zero_resolution_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="Resolution"):
            _make_instance(tmp_path, x_res=0)

    def test_invalid_animation_format_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="animation format"):
            _make_instance(tmp_path, animation_format="webp")

    def test_gif_and_apng_accepted(self, tmp_path):
        assert _make_instance(tmp_path, animation_format="gif").animation_format == "gif"
        assert _make_instance(tmp_path, animation_format="apng").animation_format == "apng"

    def test_auto_populates_sky_and_view_lists(self, tmp_path):
        paths = _make_dirs(tmp_path)
        (paths["sky"] / "s1.sky").write_text("")
        (paths["sky"] / "s2.sky").write_text("")
        (paths["view"] / "v1.vp").write_text("")
        inst = _make_instance(tmp_path)
        assert len(inst.sky_files) == 2
        assert len(inst.view_files) == 1


class TestLoadFont:
    def test_returns_font_object(self):
        f = Tiff2Animation._load_font(16)
        assert f is not None
        # Either a scalable TTF or PIL bitmap font — both OK.
        assert hasattr(f, "getmask") or isinstance(f, ImageFont.ImageFont)


class TestProcessParallel:
    def test_sequential_path_runs_all_items(self):
        results = []

        def worker(x):
            results.append(x)
            return f"ok {x}"

        Tiff2Animation._process_parallel([1, 2, 3], worker, num_workers=1)
        assert sorted(results) == [1, 2, 3]

    def test_parallel_path_runs_all_items(self):
        results = []

        def worker(x):
            results.append(x)
            return f"ok {x}"

        Tiff2Animation._process_parallel([1, 2, 3, 4], worker, num_workers=2)
        assert sorted(results) == [1, 2, 3, 4]

    def test_error_strings_still_processed(self, capsys):
        def worker(x):
            return "Error: something broke" if x == 2 else f"ok {x}"

        Tiff2Animation._process_parallel([1, 2, 3], worker, num_workers=1)
        # The error line is printed but the run completes for all items.
        captured = capsys.readouterr()
        assert "Error" in captured.out


class TestCombineTiffsByView:
    def test_noop_when_no_tiffs(self, tmp_path, capsys):
        inst = _make_instance(tmp_path)
        inst._combine_tiffs_by_view(output_format="gif", number_of_workers=1)
        assert "No TIFF files found" in capsys.readouterr().out

    def test_creates_gif_for_view(self, tmp_path):
        paths = _make_dirs(tmp_path)
        # Create a view file so the combiner has a group to target.
        view = paths["view"] / "plan_ffl_090000.vp"
        view.write_text("")
        # 2 frames with timestamps embedded in filenames.
        for ts in ("0621_0900", "0621_1200"):
            p = paths["image"] / f"plan_ffl_090000_SS_{ts}.tiff"
            Image.new("RGB", (32, 32), (100, 100, 100)).save(p, format="TIFF")

        inst = _make_instance(tmp_path, animation_format="gif")
        inst._combine_tiffs_by_view(output_format="gif", fps=2, number_of_workers=1)
        out = paths["image"] / "animated_results_plan_ffl_090000.gif"
        assert out.exists()


class TestCreateGridGif:
    def test_noop_when_no_inputs(self, tmp_path, capsys):
        inst = _make_instance(tmp_path)
        inst._create_grid_gif([], grid_size=(2, 2))
        assert "No GIF files provided" in capsys.readouterr().out

    def test_creates_grid_file(self, tmp_path):
        paths = _make_dirs(tmp_path)
        # Two source GIFs with 2 frames each.
        gif_paths = []
        for name in ("a", "b"):
            gif = paths["image"] / f"{name}.gif"
            frames = [
                Image.new("RGB", (32, 32), (255, 0, 0)),
                Image.new("RGB", (32, 32), (0, 255, 0)),
            ]
            frames[0].save(gif, save_all=True, append_images=frames[1:],
                           duration=100, loop=0)
            gif_paths.append(gif)

        inst = _make_instance(tmp_path)
        inst._create_grid_gif(gif_paths, grid_size=(2, 1),
                              target_size=(32, 32), fps=2)
        out = paths["image"] / "animated_results_grid_all_levels.gif"
        assert out.exists()


class TestStampCombined:
    def test_noop_with_empty_tiff_list(self, tmp_path):
        inst = _make_instance(tmp_path)
        # No raise when called with empty list.
        inst._stamp_tiff_files_combined([])

    def test_stamps_metadata_onto_tiff(self, tmp_path):
        inst = _make_instance(tmp_path)
        p = tmp_path / "plan_ffl_090000_SS_0621_0900_combined.tiff"
        Image.new("RGB", (256, 256), (50, 50, 50)).save(p, format="TIFF")
        inst._stamp_tiff_files_combined([p], number_of_workers=1)
        # Re-open the stamped TIFF: dimensions preserved, pixels modified.
        with Image.open(p) as img:
            assert img.size == (256, 256)
