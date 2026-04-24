"""Tests for :mod:`archilume.post.hdr2png` — HDR → PNG batch conversion.

``utils.execute_new_radiance_commands`` is mocked so tests never invoke Radiance.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from archilume.post import hdr2png as hp


class TestTiffToPng:
    def test_rejects_tiny_tiff(self, tmp_path: Path):
        tiny = tmp_path / "tiny.tiff"
        tiny.write_bytes(b"x" * 100)
        ok, err = hp._tiff_to_png(tiny)
        assert ok is False
        assert err is not None and "corrupt" in err.lower()

    def test_converts_real_tiff_and_deletes_intermediate(self, tmp_path: Path):
        tiff = tmp_path / "good.tiff"
        Image.new("RGB", (64, 64), (128, 128, 128)).save(tiff, format="TIFF")
        assert tiff.stat().st_size >= 1000

        ok, err = hp._tiff_to_png(tiff)

        assert ok is True and err is None
        assert (tmp_path / "good.png").exists()
        assert not tiff.exists(), "TIFF intermediate should be deleted"

    def test_returns_error_on_unreadable(self, tmp_path: Path):
        broken = tmp_path / "broken.tiff"
        broken.write_bytes(b"\x00" * 2000)
        ok, err = hp._tiff_to_png(broken)
        assert ok is False
        assert err is not None


class TestConvertHdrsToPngs:
    def test_skips_when_png_already_exists(self, tmp_path: Path, monkeypatch):
        hdr = tmp_path / "a.hdr"
        hdr.write_bytes(b"fake")
        (tmp_path / "a.png").write_bytes(b"existing")

        called = {"n": 0}

        def fake_exec(cmds, number_of_workers=1):
            called["n"] += 1

        monkeypatch.setattr(hp.utils, "execute_new_radiance_commands", fake_exec)
        result = hp.convert_hdrs_to_pngs([hdr])
        assert result == []
        assert called["n"] == 0

    def test_runs_pipeline_produces_png_and_removes_tiff(self, tmp_path: Path, monkeypatch):
        hdr = tmp_path / "a.hdr"
        hdr.write_bytes(b"fake")

        def fake_exec(cmds, number_of_workers=1):
            Image.new("RGB", (64, 64), (200, 0, 0)).save(
                tmp_path / "a.tiff", format="TIFF",
            )

        monkeypatch.setattr(hp.utils, "execute_new_radiance_commands", fake_exec)
        pngs = hp.convert_hdrs_to_pngs([hdr])

        assert pngs == [tmp_path / "a.png"]
        assert (tmp_path / "a.png").exists()
        assert not (tmp_path / "a.tiff").exists(), "TIFF intermediate should be cleaned up"

    def test_preserves_source_resolution(self, tmp_path: Path, monkeypatch):
        hdr = tmp_path / "a.hdr"
        hdr.write_bytes(b"fake")

        def fake_exec(cmds, number_of_workers=1):
            Image.new("RGB", (257, 129), (50, 50, 50)).save(
                tmp_path / "a.tiff", format="TIFF",
            )

        monkeypatch.setattr(hp.utils, "execute_new_radiance_commands", fake_exec)
        hp.convert_hdrs_to_pngs([hdr])

        with Image.open(tmp_path / "a.png") as img:
            assert img.size == (257, 129)


class TestConvertHdrsInDir:
    def test_empty_dir_returns_empty(self, tmp_path: Path, capsys):
        result = hp.convert_hdrs_in_dir(tmp_path)
        assert result == []
        assert "No .hdr files found" in capsys.readouterr().out

    def test_scans_all_hdrs_in_dir(self, tmp_path: Path, monkeypatch):
        for stem in ("first", "second"):
            (tmp_path / f"{stem}.hdr").write_bytes(b"fake")

        def fake_exec(cmds, number_of_workers=1):
            # Radiance ran — emit the TIFFs the helper expects.
            for cmd in cmds:
                out = Path(cmd.split(" - ")[-1])
                Image.new("RGB", (32, 32), (0, 0, 0)).save(out, format="TIFF")

        monkeypatch.setattr(hp.utils, "execute_new_radiance_commands", fake_exec)
        pngs = hp.convert_hdrs_in_dir(tmp_path)

        assert sorted(p.name for p in pngs) == ["first.png", "second.png"]
