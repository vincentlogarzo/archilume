"""Detect missing/stale falsecolour & contour PNGs and orchestrate regeneration.

The Reflex app calls into here on project open and whenever the user changes
falsecolour/contour settings. All Radiance work lives in
:mod:`archilume.post.hdr_visualisation` — this module just decides *what* to
regenerate and threads settings through.
"""

from pathlib import Path
from typing import Literal

from archilume.post.hdr_visualisation import hdr2png_falsecolor, hdr2png_contour


Stream = Literal["falsecolour", "contour"]

# PNG suffix and legend filename per stream.
_STREAM_PNG_SUFFIX = {
    "falsecolour": "_df_false.png",
    "contour":     "_df_cntr.png",
}
_STREAM_LEGEND = {
    "falsecolour": "df_false_legend.png",
    "contour":     "df_cntr_legend.png",
}


def settings_changed(stream: Stream, current: dict, last_generated: dict) -> bool:
    """Return True if `current` differs from the last_generated record for `stream`."""
    last = (last_generated or {}).get(stream) or {}
    if (
        float(current.get("scale", 0))  != float(last.get("scale", -1)) or
        int(current.get("n_levels", 0)) != int(last.get("n_levels", -1))
    ):
        return True
    # Palette only applies to the falsecolour stream; contour ignores it.
    if stream == "falsecolour":
        if str(current.get("palette", "")) != str(last.get("palette", "")):
            return True
    return False


def detect_stale(
    stream:         Stream,
    hdr_files:      list[dict],
    image_dir:      Path,
    current:        dict,
    last_generated: dict,
) -> list[Path]:
    """Return HDR paths that need (re)generation for the given stream.

    If settings changed vs `last_generated`, every HDR is stale. Otherwise we
    only regenerate HDRs whose PNG is missing or older than the source HDR.
    """
    hdr_paths = [Path(h["hdr_path"]) for h in hdr_files]
    if settings_changed(stream, current, last_generated):
        return hdr_paths

    suffix = _STREAM_PNG_SUFFIX[stream]
    stale: list[Path] = []
    for hdr in hdr_paths:
        png = image_dir / f"{hdr.stem}{suffix}"
        if not png.exists():
            stale.append(hdr)
            continue
        try:
            if hdr.stat().st_mtime > png.stat().st_mtime:
                stale.append(hdr)
        except OSError:
            stale.append(hdr)
    return stale


def invalidate_legend(stream: Stream, image_dir: Path) -> None:
    """Delete the legend PNG so the existence-guarded generator recreates it."""
    legend = image_dir / _STREAM_LEGEND[stream]
    if legend.exists():
        legend.unlink()


def regenerate_one(
    stream:    Stream,
    hdr_path:  Path,
    image_dir: Path,
    settings:  dict,
    workers:   int = 1,
) -> None:
    """Regenerate a single HDR's PNG for the given stream."""
    scale_top       = float(settings.get("scale", 4.0))
    scale_divisions = int(settings.get("n_levels", 20))
    if stream == "falsecolour":
        palette = str(settings.get("palette", "spec"))
        hdr2png_falsecolor(
            hdr_path, image_dir,
            scale_top=scale_top, scale_divisions=scale_divisions, workers=workers,
            palette=palette,
        )
    else:
        hdr2png_contour(
            hdr_path, image_dir,
            scale_top=scale_top, scale_divisions=scale_divisions, workers=workers,
        )


def radiance_available() -> bool:
    """True if the Radiance ``falsecolor`` binary can be located."""
    try:
        from archilume import config
        cand = config.RADIANCE_BIN_PATH / "falsecolor"
        return cand.exists() or cand.with_suffix(".exe").exists()
    except Exception:
        return False
