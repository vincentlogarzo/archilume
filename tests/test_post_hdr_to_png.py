"""Tests for :mod:`archilume.post.hdr_to_png` — HDR → TIFF → PNG batch conversion.

Covers all 3 public + private callables. ``utils.execute_new_radiance_commands``
is mocked so tests never invoke Radiance binaries.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from archilume.post import hdr_to_png as hp


class TestHdrsToTiffCommands:
    def test_empty_input_returns_empty(self):
        cmds, tiffs = hp.hdrs_to_tiff_commands([])
        assert cmds == [] and tiffs == []

    def test_one_command_per_hdr(self):
        hdrs = [Path("a.hdr"), Path("b.hdr")]
        cmds, tiffs = hp.hdrs_to_tiff_commands(hdrs)
        assert len(cmds) == 2
        assert len(tiffs) == 2

    def test_tiff_paths_match_hdr_stems(self):
        cmds, tiffs = hp.hdrs_to_tiff_commands([Path("/tmp/scene.hdr")])
        assert tiffs[0] == Path("/tmp/scene.tiff")

    def test_command_uses_pfilt_and_ra_tiff(self):
        cmds, _ = hp.hdrs_to_tiff_commands([Path("a.hdr")])
        assert "pfilt" in cmds[0]
        assert "ra_tiff" in cmds[0]


class TestTiffToPng:
    def test_rejects_tiny_tiff(self, tmp_path):
        tiny = tmp_path / "tiny.tiff"
        tiny.write_bytes(b"x" * 100)
        ok, err = hp._tiff_to_png(tiny)
        assert ok is False
        assert err is not None and "corrupt" in err.lower()

    def test_converts_real_tiff_to_png(self, tmp_path):
        tiff = tmp_path / "good.tiff"
        # Tiff must be >1000 bytes to pass the size gate.
        Image.new("RGB", (64, 64), (128, 128, 128)).save(tiff, format="TIFF")
        assert tiff.stat().st_size >= 1000
        ok, err = hp._tiff_to_png(tiff)
        assert ok is True and err is None
        assert (tmp_path / "good.png").exists()

    def test_returns_error_on_unreadable(self, tmp_path):
        broken = tmp_path / "broken.tiff"
        broken.write_bytes(b"\x00" * 2000)  # big but not a valid tiff
        ok, err = hp._tiff_to_png(broken)
        assert ok is False
        assert err is not None


class TestConvertHdrsToPngs:
    def test_skips_when_png_already_exists(self, tmp_path, monkeypatch, capsys):
        hdr = tmp_path / "a.hdr"
        hdr.write_bytes(b"fake")
        (tmp_path / "a.png").write_bytes(b"existing")

        called = {"n": 0}

        def fake_exec(cmds, number_of_workers=1):
            called["n"] += 1

        monkeypatch.setattr(hp.utils, "execute_new_radiance_commands", fake_exec)
        result = hp.convert_hdrs_to_pngs([hdr])
        assert result == []
        assert called["n"] == 0  # pipeline skipped entirely

    def test_runs_pipeline_and_converts_tiff_to_png(self, tmp_path, monkeypatch):
        hdr = tmp_path / "a.hdr"
        hdr.write_bytes(b"fake")

        def fake_exec(cmds, number_of_workers=1):
            # Simulate Radiance creating the expected .tiff.
            Image.new("RGB", (64, 64), (200, 0, 0)).save(
                tmp_path / "a.tiff", format="TIFF",
            )

        monkeypatch.setattr(hp.utils, "execute_new_radiance_commands", fake_exec)
        pngs = hp.convert_hdrs_to_pngs([hdr])
        assert pngs == [tmp_path / "a.png"]
        assert (tmp_path / "a.png").exists()
