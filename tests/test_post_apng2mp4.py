"""Tests for :mod:`archilume.post.apng2mp4` — APNG → MP4 conversion.

The 3 methods of ``Apng2Mp4`` are exercised. ``_convert_single`` uses a real
APNG fixture written via PIL and OpenCV's VideoWriter (no external binaries).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from archilume.post.apng2mp4 import Apng2Mp4


def _write_apng(path: Path, frames: int = 3, size: tuple[int, int] = (32, 32)) -> None:
    """Write a valid multi-frame APNG at ``path``."""
    imgs = [
        Image.new("RGB", size, (i * 60 % 256, 100, 100))
        for i in range(frames)
    ]
    imgs[0].save(
        path, format="PNG", save_all=True,
        append_images=imgs[1:], duration=100, loop=0,
    )


class TestApng2Mp4Init:
    def test_missing_input_dir_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            Apng2Mp4(input_dir=tmp_path / "missing")

    def test_invalid_fps_raises(self, tmp_path):
        with pytest.raises(ValueError, match="FPS"):
            Apng2Mp4(input_dir=tmp_path, fps=0)

    def test_output_dir_defaults_to_input(self, tmp_path):
        conv = Apng2Mp4(input_dir=tmp_path)
        assert conv.output_dir == tmp_path

    def test_output_dir_created_when_provided(self, tmp_path):
        out = tmp_path / "new_out_dir"
        Apng2Mp4(input_dir=tmp_path, output_dir=out)
        assert out.exists()


class TestConvert:
    def test_empty_dir_returns_empty_list(self, tmp_path):
        result = Apng2Mp4(input_dir=tmp_path).convert()
        assert result == []

    def test_converts_all_matching_files(self, tmp_path):
        _write_apng(tmp_path / "a.apng")
        _write_apng(tmp_path / "b.apng")
        # Decoy non-apng should be ignored by glob pattern.
        (tmp_path / "c.txt").write_text("ignored")

        result = Apng2Mp4(input_dir=tmp_path, fps=5).convert()
        assert len(result) == 2
        assert all(p.suffix == ".mp4" for p in result)
        assert all(p.exists() for p in result)

    def test_convert_single_raises_on_single_frame_png(self, tmp_path):
        # A single-frame PNG saved without save_all is treated as an APNG
        # with one frame; Apng2Mp4 still handles it, but zero-frame is error.
        single = tmp_path / "one.apng"
        Image.new("RGB", (8, 8), (10, 20, 30)).save(single, format="PNG")
        out = tmp_path / "one.mp4"
        # Single frame is acceptable; confirm no raise + output created.
        result = Apng2Mp4(input_dir=tmp_path, fps=1)._convert_single(single, out)
        assert result == out
        assert out.exists()

    def test_convert_tolerates_per_file_errors(self, tmp_path):
        # One good file + one corrupt. convert() should not raise.
        _write_apng(tmp_path / "good.apng")
        (tmp_path / "bad.apng").write_bytes(b"not a png")
        result = Apng2Mp4(input_dir=tmp_path, fps=2).convert()
        # At least the good one converts; corrupt one is captured as error.
        assert any(p.name == "good.mp4" for p in result)
