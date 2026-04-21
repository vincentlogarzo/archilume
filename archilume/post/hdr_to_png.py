"""HDR -> PNG batch conversion.

Converts every ``*.hdr`` in a directory (or an explicit list) to a compact
PNG sibling at the source image's native resolution. Uses Radiance
``pfilt -1 | ra_tiff -e -4`` for tone mapping, then PIL to re-encode the
TIFF as PNG. The TIFF intermediate is deleted once the PNG is written so
only compact PNGs are left on disk.

The archilume-app reads the PNGs directly; per-frame sun / overcast
compositing now happens in the app, not in this module.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

from PIL import Image

from archilume import config, utils


def _tiff_to_png(tiff: Path) -> tuple[bool, str | None]:
    """Re-encode a tone-mapped TIFF as PNG at the same resolution, then delete the TIFF."""
    if tiff.stat().st_size < 1000:
        return False, f"corrupt/empty TIFF ({tiff.stat().st_size} bytes)"
    try:
        Image.open(tiff).save(
            tiff.with_suffix(".png"),
            format="PNG",
            optimize=False,
            compress_level=6,
        )
        tiff.unlink(missing_ok=True)
        return True, None
    except Exception as exc:
        return False, str(exc)


def convert_hdrs_to_pngs(hdr_paths: Iterable[Path]) -> list[Path]:
    """Write a compact ``{stem}.png`` next to every HDR in ``hdr_paths``.

    Skips HDRs whose ``.png`` already exists (idempotent re-run). The
    tone-mapped TIFF intermediate is removed after the PNG is written.
    """
    hdrs = [h for h in hdr_paths if not h.with_suffix(".png").exists()]
    if not hdrs:
        print("All HDRs already have .png siblings — nothing to convert.")
        return []

    print(f"Converting {len(hdrs)} HDR files -> PNG...")

    tiffs = [h.with_suffix(".tiff") for h in hdrs]
    cmds = [rf"pfilt -1 {h} | ra_tiff -e -4 - {t}" for h, t in zip(hdrs, tiffs)]
    utils.execute_new_radiance_commands(
        cmds, number_of_workers=config.WORKERS["pcomb_tiff_conversion"]
    )

    pngs: list[Path] = []
    failed = 0
    max_workers = min(config.WORKERS["metadata_stamping"], len(tiffs))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_tiff_to_png, t): t for t in tiffs}
        for fut in as_completed(futures):
            tiff = futures[fut]
            ok, err = fut.result()
            if ok:
                pngs.append(tiff.with_suffix(".png"))
            else:
                failed += 1
                print(f"WARNING: PNG conversion failed for {tiff.name}: {err}")

    print(f"Converted {len(pngs)} PNGs ({failed} failures).")
    return pngs


def convert_hdrs_in_dir(image_dir: Path) -> list[Path]:
    """Convert every ``*.hdr`` in ``image_dir`` to a PNG sibling.

    Thin directory-scanning wrapper over :func:`convert_hdrs_to_pngs`.
    """
    hdrs = sorted(image_dir.glob("*.hdr"))
    if not hdrs:
        print(f"No .hdr files found in {image_dir}")
        return []
    return convert_hdrs_to_pngs(hdrs)
