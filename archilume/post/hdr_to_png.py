"""HDR -> TIFF -> PNG batch conversion.

Used by SunlightRenderer.sun_only_rendering_pipeline so the rendering phase
emits browser-ready .png siblings next to each .hdr. The archilume-app then
reads PNGs directly without any per-frame tone-mapping.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

from PIL import Image

from archilume import config, utils


def hdrs_to_tiff_commands(hdr_paths: Iterable[Path]) -> tuple[list[str], list[Path]]:
    """Build one `pfilt | ra_tiff` command per HDR.

    Returns (commands, tiff_paths) so callers can execute the commands in
    parallel and then post-process the resulting TIFFs in the same order.
    """
    cmds: list[str] = []
    tiffs: list[Path] = []
    for hdr in hdr_paths:
        tiff = hdr.with_suffix(".tiff")
        cmds.append(rf"pfilt -1 {hdr} | ra_tiff -e -4 - {tiff}")
        tiffs.append(tiff)
    return cmds, tiffs


def _tiff_to_png(tiff: Path) -> tuple[bool, str | None]:
    if tiff.stat().st_size < 1000:
        return False, f"corrupt/empty TIFF ({tiff.stat().st_size} bytes)"
    try:
        Image.open(tiff).save(
            tiff.with_suffix(".png"),
            format="PNG",
            optimize=False,
            compress_level=6,
        )
        return True, None
    except Exception as exc:
        return False, str(exc)


def convert_hdrs_to_pngs(hdr_paths: Iterable[Path]) -> list[Path]:
    """Render `{stem}.tiff` and `{stem}.png` next to every HDR.

    Skips HDRs whose .png already exists (idempotent re-run). TIFF intermediates
    are left in place for downstream tools that consume them.
    """
    hdrs = [h for h in hdr_paths if not h.with_suffix(".png").exists()]
    if not hdrs:
        print("All HDRs already have .png siblings — nothing to convert.")
        return []

    print(f"Converting {len(hdrs)} HDR files -> TIFF -> PNG...")

    cmds, tiffs = hdrs_to_tiff_commands(hdrs)
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
