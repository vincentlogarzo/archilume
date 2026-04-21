"""Tests for :mod:`archilume.post.hdr_visualisation` — falsecolour + contour PNGs.

Covers all 7 callables. Radiance execution is mocked so no external binaries
are required; post-Radiance PIL conversions use real TIFFs written by the mock.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from archilume.post import hdr_visualisation as hv


# =========================================================================
# _coerce_vis_params
# =========================================================================


class TestCoerceVisParams:
    def test_clamps_scale_top_above_max(self, caplog):
        top, div = hv._coerce_vis_params(50.0, 5, context="test")
        assert top == hv.SCALE_TOP_MAX

    def test_clamps_scale_top_below_min(self):
        top, _ = hv._coerce_vis_params(-5.0, 5, context="test")
        assert top == hv.SCALE_TOP_MIN

    def test_snaps_to_step(self):
        # step = 0.5 → 3.3 snaps to 3.5.
        top, _ = hv._coerce_vis_params(3.3, 5, context="test")
        assert top == 3.5

    def test_clamps_divisions(self):
        _, d = hv._coerce_vis_params(4.0, 50, context="test")
        assert d == hv.SCALE_DIVISIONS_MAX

        _, d = hv._coerce_vis_params(4.0, -3, context="test")
        assert d == hv.SCALE_DIVISIONS_MIN

    def test_handles_non_numeric_input(self):
        top, div = hv._coerce_vis_params("bad", "worse", context="test")
        assert top == hv.SCALE_TOP_MIN
        assert div == hv.SCALE_DIVISIONS_MIN

    def test_returns_tuple_of_numeric(self):
        top, div = hv._coerce_vis_params(4.0, 10, context="test")
        assert isinstance(top, float)
        assert isinstance(div, int)


# =========================================================================
# _log_intermediate
# =========================================================================


class TestLogIntermediate:
    def test_returns_false_when_missing(self, tmp_path, capsys):
        assert hv._log_intermediate("x", tmp_path / "missing.tiff") is False

    def test_returns_false_when_too_small(self, tmp_path):
        p = tmp_path / "small.tiff"
        p.write_bytes(b"x" * 100)
        assert hv._log_intermediate("x", p) is False

    def test_returns_true_when_large_enough(self, tmp_path):
        p = tmp_path / "big.tiff"
        p.write_bytes(b"x" * 2000)
        assert hv._log_intermediate("x", p) is True


# =========================================================================
# _tiff_to_png
# =========================================================================


class TestTiffToPng:
    def test_silent_noop_when_tiff_missing(self, tmp_path):
        hv._tiff_to_png(tmp_path / "nope.tiff")  # no raise
        assert not (tmp_path / "nope.png").exists()

    def test_too_small_tiff_deleted(self, tmp_path):
        tiny = tmp_path / "tiny.tiff"
        tiny.write_bytes(b"x" * 100)
        hv._tiff_to_png(tiny)
        assert not tiny.exists()

    def test_converts_and_removes_source(self, tmp_path):
        tiff = tmp_path / "good.tiff"
        Image.new("RGB", (64, 64), (0, 255, 0)).save(tiff, format="TIFF")
        assert tiff.stat().st_size >= 1000
        hv._tiff_to_png(tiff)
        assert (tmp_path / "good.png").exists()
        assert not tiff.exists()  # source deleted after conversion


# =========================================================================
# hdr2png_falsecolor + hdr2png_contour — Radiance mocked
# =========================================================================


def _make_fake_tiff(path: Path, size: tuple[int, int] = (64, 64)) -> None:
    """Helper — write a real PIL TIFF at the given path."""
    Image.new("RGB", size, (100, 100, 100)).save(path, format="TIFF")


class TestFalsecolorAndContour:
    def test_falsecolor_rejects_invalid_palette(self, tmp_path):
        hdr = tmp_path / "x.hdr"
        hdr.write_bytes(b"")
        with pytest.raises(ValueError, match="palette"):
            hv.hdr2png_falsecolor(hdr, tmp_path, palette="pink")

    def test_falsecolor_writes_png(self, tmp_path, monkeypatch):
        hdr = tmp_path / "view_a.hdr"
        hdr.write_bytes(b"")

        def fake_exec(cmds, number_of_workers=1):
            # Mock Radiance produces the falsecolour TIFF.
            _make_fake_tiff(tmp_path / "view_a_df_false.tiff")
            # Legend TIFF path varies — write if requested by legend generation.
            legend_path = tmp_path / "df_false_legend.tiff"
            if not legend_path.exists():
                _make_fake_tiff(legend_path)

        monkeypatch.setattr(hv.utils, "execute_new_radiance_commands", fake_exec)

        hv.hdr2png_falsecolor(hdr, tmp_path, scale_top=4.0, scale_divisions=10)
        assert (tmp_path / "view_a_df_false.png").exists()

    def test_contour_writes_png(self, tmp_path, monkeypatch):
        hdr = tmp_path / "view_b.hdr"
        hdr.write_bytes(b"")

        def fake_exec(cmds, number_of_workers=1):
            # Contour pipeline produces an intermediate dimmed + contour HDR,
            # then a composite TIFF.
            (tmp_path / "view_b_dimmed_temp.hdr").write_bytes(b"x" * 2000)
            (tmp_path / "view_b_df_cntr.hdr").write_bytes(b"x" * 2000)
            _make_fake_tiff(tmp_path / "view_b_df_cntr.tiff")
            legend_path = tmp_path / "df_cntr_legend.tiff"
            if not legend_path.exists():
                _make_fake_tiff(legend_path)

        monkeypatch.setattr(hv.utils, "execute_new_radiance_commands", fake_exec)

        hv.hdr2png_contour(hdr, tmp_path, scale_top=2.0, scale_divisions=4)
        assert (tmp_path / "view_b_df_cntr.png").exists()


# =========================================================================
# Legend generation — idempotency check
# =========================================================================


class TestLegends:
    def test_falsecolor_legend_idempotent(self, tmp_path, monkeypatch):
        # If the legend PNG already exists, no Radiance call should be issued.
        (tmp_path / "df_false_legend.png").write_bytes(b"existing")
        called = {"n": 0}
        monkeypatch.setattr(hv.utils, "execute_new_radiance_commands",
                            lambda *a, **kw: called.__setitem__("n", called["n"] + 1))
        hv._generate_falsecolor_legend(tmp_path, 4.0, 10, 1)
        assert called["n"] == 0

    def test_contour_legend_idempotent(self, tmp_path, monkeypatch):
        (tmp_path / "df_cntr_legend.png").write_bytes(b"existing")
        called = {"n": 0}
        monkeypatch.setattr(hv.utils, "execute_new_radiance_commands",
                            lambda *a, **kw: called.__setitem__("n", called["n"] + 1))
        hv._generate_contour_legend(tmp_path, 2.0, 4, 1)
        assert called["n"] == 0

    def test_falsecolor_legend_writes_png(self, tmp_path, monkeypatch):
        def fake_exec(cmds, number_of_workers=1):
            _make_fake_tiff(tmp_path / "df_false_legend.tiff")

        monkeypatch.setattr(hv.utils, "execute_new_radiance_commands", fake_exec)
        hv._generate_falsecolor_legend(tmp_path, 4.0, 10, 1)
        assert (tmp_path / "df_false_legend.png").exists()
