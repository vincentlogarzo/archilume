"""Tests for ``visualisation_manager.detect_stale`` — existence-only gating.

After the cache/regen discipline refactor, ``detect_stale`` regenerates a
timestep's PNG only when the PNG file is missing from ``image_dir``. mtime
staleness and settings-change auto-trigger both go through the force=True
path (UI "Regenerate" button), not this function.

Regression locks:
- mtime(HDR) > mtime(PNG) must NOT trigger regen
- settings change must NOT trigger regen (no current/last_generated params)
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from archilume_app.lib import visualisation_manager as vm


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _touch(path: Path, *, content: bytes = b"x") -> Path:
    path.write_bytes(content)
    return path


@pytest.fixture
def image_dir(tmp_path: Path) -> Path:
    d = tmp_path / "image"
    d.mkdir()
    return d


def _hdr_dict(hdr_path: Path) -> dict:
    """Shape matches ``scan_hdr_files`` dicts used by the state layer."""
    return {"hdr_path": str(hdr_path)}


# ---------------------------------------------------------------------------
# Existence gating
# ---------------------------------------------------------------------------


class TestDetectStaleExistence:
    def test_png_missing_marks_hdr_stale(self, image_dir: Path) -> None:
        hdr = _touch(image_dir / "frame_01.hdr")
        stale = vm.detect_stale("falsecolour", [_hdr_dict(hdr)], image_dir)
        assert stale == [hdr]

    def test_png_present_skips_hdr(self, image_dir: Path) -> None:
        hdr = _touch(image_dir / "frame_01.hdr")
        _touch(image_dir / "frame_01_df_false.png")
        assert vm.detect_stale("falsecolour", [_hdr_dict(hdr)], image_dir) == []

    def test_contour_uses_correct_suffix(self, image_dir: Path) -> None:
        hdr = _touch(image_dir / "frame_01.hdr")
        _touch(image_dir / "frame_01_df_cntr.png")
        # falsecolour PNG missing → stale for falsecolour stream
        assert vm.detect_stale("falsecolour", [_hdr_dict(hdr)], image_dir) == [hdr]
        # contour PNG present → not stale for contour stream
        assert vm.detect_stale("contour", [_hdr_dict(hdr)], image_dir) == []

    def test_mixed_present_and_missing(self, image_dir: Path) -> None:
        a = _touch(image_dir / "a.hdr")
        b = _touch(image_dir / "b.hdr")
        c = _touch(image_dir / "c.hdr")
        _touch(image_dir / "a_df_false.png")
        # b's PNG missing, c's PNG missing
        _touch(image_dir / "c_df_false.png")
        stale = vm.detect_stale(
            "falsecolour",
            [_hdr_dict(a), _hdr_dict(b), _hdr_dict(c)],
            image_dir,
        )
        assert stale == [b]

    def test_empty_hdr_list_returns_empty(self, image_dir: Path) -> None:
        assert vm.detect_stale("falsecolour", [], image_dir) == []


# ---------------------------------------------------------------------------
# Regression locks — behaviour that used to trigger regen must NOT anymore
# ---------------------------------------------------------------------------


class TestDetectStaleRegressions:
    def test_hdr_newer_than_png_is_not_stale(self, image_dir: Path) -> None:
        """mtime check is gone: fresh HDR next to an existing PNG is fine."""
        hdr = _touch(image_dir / "frame.hdr")
        png = _touch(image_dir / "frame_df_false.png")
        # Age the PNG so it's older than the HDR.
        old = time.time() - 3600
        os.utime(png, (old, old))
        now = time.time()
        os.utime(hdr, (now, now))

        assert hdr.stat().st_mtime > png.stat().st_mtime
        assert vm.detect_stale("falsecolour", [_hdr_dict(hdr)], image_dir) == []

    def test_signature_no_longer_takes_settings(self, image_dir: Path) -> None:
        """detect_stale must not accept current / last_generated kwargs.

        Catches regressions where a caller still passes the old 5-arg signature.
        """
        import inspect
        sig = inspect.signature(vm.detect_stale)
        assert set(sig.parameters.keys()) == {"stream", "hdr_files", "image_dir"}


# ---------------------------------------------------------------------------
# settings_changed — kept as a standalone helper for the force=True path
# ---------------------------------------------------------------------------


class TestSettingsChangedHelper:
    def test_returns_true_when_scale_differs(self) -> None:
        current = {"scale": 4.0, "n_levels": 10, "palette": "spec"}
        last = {"falsecolour": {"scale": 2.0, "n_levels": 10, "palette": "spec"}}
        assert vm.settings_changed("falsecolour", current, last) is True

    def test_returns_false_on_match(self) -> None:
        current = {"scale": 4.0, "n_levels": 10, "palette": "spec"}
        last = {"falsecolour": {"scale": 4.0, "n_levels": 10, "palette": "spec"}}
        assert vm.settings_changed("falsecolour", current, last) is False

    def test_palette_ignored_for_contour(self) -> None:
        current = {"scale": 2.0, "n_levels": 4, "palette": "spec"}
        last = {"contour": {"scale": 2.0, "n_levels": 4, "palette": "def"}}
        assert vm.settings_changed("contour", current, last) is False
