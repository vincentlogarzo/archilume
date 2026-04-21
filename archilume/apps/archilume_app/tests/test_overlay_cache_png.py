"""Tests for the compressed-PNG PDF overlay disk cache.

Covers ``rasterize_pdf_page`` and ``rasterize_pdf_page_to_cache`` after the
switch from uncompressed ``.npy`` arrays to deflated ``.png`` files served as
Reflex static URLs.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
import pytest
from PIL import Image

from archilume_app.lib.image_loader import (
    _overlay_cache_path,
    rasterize_pdf_page,
    rasterize_pdf_page_to_cache,
)


def _make_pdf(target: Path, *, pages: int = 1, text: str = "Hello") -> Path:
    """Create a tiny deterministic PDF at *target*. Returns the path."""
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=200, height=150)
        page.insert_text((20, 40), f"{text} {i}", fontsize=14)
    doc.save(str(target))
    doc.close()
    return target


@pytest.fixture
def pdf_path(tmp_path: Path) -> Path:
    return _make_pdf(tmp_path / "plan.pdf")


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "overlay_cache"


# ---------------------------------------------------------------------------
# rasterize_pdf_page — returns (cache_path, w, h)
# ---------------------------------------------------------------------------


def test_cache_miss_creates_png_and_returns_path(
    pdf_path: Path, cache_dir: Path,
) -> None:
    result_path, w, h = rasterize_pdf_page(pdf_path, page_index=0, dpi=150, cache_dir=cache_dir)

    assert result_path is not None
    assert result_path.parent == cache_dir
    assert result_path.suffix == ".png"
    assert result_path.exists()
    assert w > 0 and h > 0

    expected = _overlay_cache_path(pdf_path, 0, 150, cache_dir)
    assert result_path == expected


def test_cache_hit_returns_same_path_without_rewriting(
    pdf_path: Path, cache_dir: Path,
) -> None:
    path_first, w1, h1 = rasterize_pdf_page(pdf_path, 0, 150, cache_dir=cache_dir)
    mtime_before = path_first.stat().st_mtime_ns

    path_second, w2, h2 = rasterize_pdf_page(pdf_path, 0, 150, cache_dir=cache_dir)
    mtime_after = path_second.stat().st_mtime_ns

    assert path_first == path_second
    assert (w1, h1) == (w2, h2)
    assert mtime_before == mtime_after  # no rewrite on hit


def test_missing_pdf_returns_none_triple(tmp_path: Path, cache_dir: Path) -> None:
    missing = tmp_path / "nope.pdf"
    assert rasterize_pdf_page(missing, 0, 150, cache_dir=cache_dir) == (None, 0, 0)


def test_missing_cache_dir_returns_none_triple(pdf_path: Path) -> None:
    # No cache_dir → no location to write the PNG.
    assert rasterize_pdf_page(pdf_path, 0, 150, cache_dir=None) == (None, 0, 0)


def test_page_out_of_range_returns_none_triple(
    pdf_path: Path, cache_dir: Path,
) -> None:
    assert rasterize_pdf_page(pdf_path, page_index=5, dpi=150, cache_dir=cache_dir) == (
        None, 0, 0,
    )


def test_different_dpi_produces_different_cache_entries(
    pdf_path: Path, cache_dir: Path,
) -> None:
    rasterize_pdf_page(pdf_path, 0, 150, cache_dir=cache_dir)
    rasterize_pdf_page(pdf_path, 0, 300, cache_dir=cache_dir)

    files = sorted(cache_dir.glob("*.png"))
    assert len(files) == 2
    assert any("150dpi" in f.name for f in files)
    assert any("300dpi" in f.name for f in files)


def test_fingerprint_changes_on_pdf_edit(
    pdf_path: Path, cache_dir: Path,
) -> None:
    """Replacing the PDF at the same path must yield a new cache filename."""
    _, _, _ = rasterize_pdf_page(pdf_path, 0, 150, cache_dir=cache_dir)
    first = sorted(cache_dir.glob("*.png"))
    assert len(first) == 1

    # Overwrite with different content — size/mtime change → new fingerprint.
    _make_pdf(pdf_path, pages=2, text="Different")

    _, _, _ = rasterize_pdf_page(pdf_path, 0, 150, cache_dir=cache_dir)
    all_files = sorted(cache_dir.glob("*.png"))
    assert len(all_files) == 2  # old orphan + fresh entry


def test_png_cache_is_valid_image(pdf_path: Path, cache_dir: Path) -> None:
    cache_path, w, h = rasterize_pdf_page(pdf_path, 0, 150, cache_dir=cache_dir)
    with Image.open(cache_path) as img:
        assert img.format == "PNG"
        assert img.size == (w, h)


def test_no_tmp_files_remain_after_successful_write(
    pdf_path: Path, cache_dir: Path,
) -> None:
    rasterize_pdf_page(pdf_path, 0, 150, cache_dir=cache_dir)
    assert list(cache_dir.glob("*.tmp.png")) == []


def test_png_is_much_smaller_than_equivalent_npy(
    pdf_path: Path, cache_dir: Path,
) -> None:
    """Sanity check the primary motivation — PNG deflate beats raw RGB."""
    rasterize_pdf_page(pdf_path, 0, 150, cache_dir=cache_dir)
    cache_path = _overlay_cache_path(pdf_path, 0, 150, cache_dir)
    with Image.open(cache_path) as img:
        w, h = img.size
    raw_rgb_bytes = w * h * 3
    png_bytes = cache_path.stat().st_size
    assert png_bytes < raw_rgb_bytes  # PNG must be smaller than uncompressed RGB


# ---------------------------------------------------------------------------
# rasterize_pdf_page_to_cache — prefetch path
# ---------------------------------------------------------------------------


def test_prefetch_writes_png_and_returns_true(
    pdf_path: Path, cache_dir: Path,
) -> None:
    ok = rasterize_pdf_page_to_cache(pdf_path, 0, 200, cache_dir)
    assert ok is True
    cache_path = _overlay_cache_path(pdf_path, 0, 200, cache_dir)
    assert cache_path.exists()
    assert cache_path.suffix == ".png"


def test_prefetch_skips_when_cache_exists(
    pdf_path: Path, cache_dir: Path,
) -> None:
    rasterize_pdf_page_to_cache(pdf_path, 0, 200, cache_dir)
    cache_path = _overlay_cache_path(pdf_path, 0, 200, cache_dir)
    mtime_before = cache_path.stat().st_mtime_ns

    ok = rasterize_pdf_page_to_cache(pdf_path, 0, 200, cache_dir)
    assert ok is True
    assert cache_path.stat().st_mtime_ns == mtime_before


def test_prefetch_missing_pdf_returns_false(
    tmp_path: Path, cache_dir: Path,
) -> None:
    missing = tmp_path / "nope.pdf"
    assert rasterize_pdf_page_to_cache(missing, 0, 150, cache_dir) is False


def test_prefetch_page_out_of_range_returns_false(
    pdf_path: Path, cache_dir: Path,
) -> None:
    assert rasterize_pdf_page_to_cache(pdf_path, 9, 150, cache_dir) is False
