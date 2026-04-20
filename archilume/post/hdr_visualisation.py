"""HDR visualisation post-processing — falsecolour + contour PNGs.

Two independent public functions, one per visualisation stream:

  - :func:`hdr2png_falsecolor` — spectral falsecolour PNG ``*_df_false.png``
                                  + ``df_false_legend.png``
  - :func:`hdr2png_contour`    — contour overlay PNG ``*_df_cntr.png``
                                  + ``df_cntr_legend.png``

Each owns its own ``scale_top`` / ``scale_divisions`` parameters so callers can
tune one stream without affecting the other. Legends are existence-guarded so
the functions are safe to call in a loop over many HDRs.
"""

# Archilume imports
from archilume import utils

# Standard library imports
from pathlib import Path
import logging

# Third-party imports
from PIL import Image

logger = logging.getLogger(__name__)

# Validation bounds — shared with the UI setters in editor_state.py.
SCALE_TOP_MIN       = 0.0
SCALE_TOP_MAX       = 10.0
SCALE_TOP_STEP      = 0.5
SCALE_DIVISIONS_MIN = 0
SCALE_DIVISIONS_MAX = 10

# Palette names accepted by the Radiance `falsecolor -pal` flag.
FALSECOLOR_PALETTES = ("spec", "def", "pm3d", "hot", "eco", "tbo")
DEFAULT_FALSECOLOR_PALETTE = "spec"


def _coerce_vis_params(
    scale_top: float, scale_divisions: int, *, context: str,
) -> tuple[float, int]:
    """Snap & clamp inputs so Radiance never sees malformed values.

    - scale_top → clamped to [SCALE_TOP_MIN, SCALE_TOP_MAX], snapped to the
      nearest SCALE_TOP_STEP (0.5), rounded to 1 decimal place.
    - scale_divisions → int(round(...)), clamped to
      [SCALE_DIVISIONS_MIN, SCALE_DIVISIONS_MAX].

    Logs at WARNING level whenever coercion changes the value, so badly-typed
    callers (not just the UI) get visible feedback.
    """
    try:
        raw_top = float(scale_top)
    except (TypeError, ValueError):
        raw_top = SCALE_TOP_MIN
    snapped_top = round(
        max(SCALE_TOP_MIN, min(SCALE_TOP_MAX, raw_top)) / SCALE_TOP_STEP
    ) * SCALE_TOP_STEP
    snapped_top = round(snapped_top, 1)
    if snapped_top != scale_top:
        logger.warning(
            "[%s] scale_top %r coerced to %s (range [%s, %s], step %s)",
            context, scale_top, snapped_top,
            SCALE_TOP_MIN, SCALE_TOP_MAX, SCALE_TOP_STEP,
        )

    try:
        raw_div = int(round(float(scale_divisions)))
    except (TypeError, ValueError):
        raw_div = SCALE_DIVISIONS_MIN
    snapped_div = max(SCALE_DIVISIONS_MIN, min(SCALE_DIVISIONS_MAX, raw_div))
    if snapped_div != scale_divisions:
        logger.warning(
            "[%s] scale_divisions %r coerced to %d (integer range [%d, %d])",
            context, scale_divisions, snapped_div,
            SCALE_DIVISIONS_MIN, SCALE_DIVISIONS_MAX,
        )

    return snapped_top, snapped_div


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def hdr2png_falsecolor(
    hdr_path:        Path,
    image_dir:       Path,
    scale_top:       float = 4.0,
    scale_divisions: int   = 10,
    workers:         int   = 1,
    palette:         str   = DEFAULT_FALSECOLOR_PALETTE,
) -> None:
    """Generate the falsecolour PNG (and legend) for a single HDR.

    Args:
        hdr_path:         Source HDR file.
        image_dir:        Output directory (PNGs land here).
        scale_top:        Maximum DF value on the palette (default 4 % DF).
        scale_divisions:  Number of falsecolour levels (default 10).
        workers:          Parallel workers for Radiance commands.
        palette:          Radiance ``falsecolor -pal`` name. One of
                          :data:`FALSECOLOR_PALETTES`.
    """
    if palette not in FALSECOLOR_PALETTES:
        raise ValueError(
            f"invalid falsecolor palette {palette!r}; "
            f"expected one of {FALSECOLOR_PALETTES}"
        )
    scale_top, scale_divisions = _coerce_vis_params(
        scale_top, scale_divisions, context="falsecolor",
    )
    stem       = hdr_path.stem
    false_tiff = image_dir / f"{stem}_df_false.tiff"

    src = hdr_path.as_posix()
    ft  = false_tiff.as_posix()

    cmd = (
        f'pcomb -s 0.01 {src} | falsecolor -s {scale_top} -n {scale_divisions} '
        f'-pal {palette} -l "DF %" -lw 0 | ra_tiff - {ft}'
    )
    print(f"[hdr_vis] Running falsecolour for: {stem}")
    utils.execute_new_radiance_commands(cmd, number_of_workers=workers)

    _log_intermediate("false_tiff", false_tiff)
    _tiff_to_png(false_tiff)

    _generate_falsecolor_legend(image_dir, scale_top, scale_divisions, workers, palette)


def hdr2png_contour(
    hdr_path:        Path,
    image_dir:       Path,
    scale_top:       float = 2.0,
    scale_divisions: int   = 4,
    workers:         int   = 1,
) -> None:
    """Generate the contour overlay PNG (and legend) for a single HDR.

    Composites a contour HDR over a dimmed copy of the source HDR so the
    contour lines remain readable against the underlying scene.

    Args:
        hdr_path:         Source HDR file.
        image_dir:        Output directory (PNGs land here).
        scale_top:        Maximum DF value on the contour palette (default 2 % DF).
        scale_divisions:  Number of contour levels (default 4).
        workers:          Parallel workers for Radiance commands.
    """
    scale_top, scale_divisions = _coerce_vis_params(
        scale_top, scale_divisions, context="contour",
    )
    stem         = hdr_path.stem
    dimmed       = image_dir / f"{stem}_dimmed_temp.hdr"
    contour_hdr  = image_dir / f"{stem}_df_cntr.hdr"
    contour_tiff = image_dir / f"{stem}_df_cntr.tiff"

    src = hdr_path.as_posix()
    ch  = contour_hdr.as_posix()
    ct  = contour_tiff.as_posix()
    dm  = dimmed.as_posix()

    cmds = [
        # Contour HDR
        f'pcomb -s 0.01 {src} | falsecolor -cl -s {scale_top} -n {scale_divisions} -l "DF %" -lw 0 -lh 0 > {ch}',
        # Dimmed background
        f"pfilt -e 0.5 {src} > {dm}",
    ]
    print(f"[hdr_vis] Running contour/dimmed for: {stem}")
    utils.execute_new_radiance_commands(cmds, number_of_workers=workers)

    _log_intermediate("contour_hdr", contour_hdr)
    _log_intermediate("dimmed",      dimmed)

    if not dimmed.exists() or not contour_hdr.exists():
        print(
            f"[hdr_vis] ERROR — Skipping contour composite "
            f"(dimmed exists={dimmed.exists()}, contour_hdr exists={contour_hdr.exists()})"
        )
    else:
        composite_cmd = (
            f'pcomb -e "cond=ri(2)+gi(2)+bi(2)" '
            f'-e "ro=if(cond-.01,ri(2),ri(1))" '
            f'-e "go=if(cond-.01,gi(2),gi(1))" '
            f'-e "bo=if(cond-.01,bi(2),bi(1))" '
            f"{dm} {ch} | ra_tiff - {ct}"
        )
        utils.execute_new_radiance_commands(composite_cmd, number_of_workers=workers)
        _log_intermediate("contour_composite", contour_tiff)

    _tiff_to_png(contour_tiff)

    # Clean up contour-specific intermediates
    for tmp in (dimmed, contour_hdr):
        if tmp.exists():
            tmp.unlink()

    _generate_contour_legend(image_dir, scale_top, scale_divisions, workers)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _tiff_to_png(tiff: Path) -> None:
    """Convert a Radiance-produced TIFF to PNG and remove the TIFF."""
    if not tiff.exists():
        print(f"[hdr_vis] ERROR — {tiff.name} does not exist, no PNG created")
        return
    if tiff.stat().st_size < 1000:
        print(f"[hdr_vis] ERROR — {tiff.name} too small for PNG conversion ({tiff.stat().st_size} bytes)")
        tiff.unlink()
        return
    png = tiff.with_suffix(".png")
    Image.open(tiff).save(png, format="PNG", optimize=True, compress_level=9)
    print(f"[hdr_vis] Created {png.name}")
    tiff.unlink()


def _log_intermediate(label: str, path: Path) -> bool:
    """Log existence + size sanity for a Radiance intermediate. Returns True if OK."""
    if not path.exists():
        print(f"[hdr_vis] ERROR — {label} not created: {path}")
        return False
    if path.stat().st_size < 1000:
        print(f"[hdr_vis] ERROR — {label} too small ({path.stat().st_size} bytes): {path}")
        return False
    print(f"[hdr_vis] {label} OK ({path.stat().st_size} bytes)")
    return True


# ---------------------------------------------------------------------------
# Legend generation (per stream, existence-guarded)
# ---------------------------------------------------------------------------


def _generate_falsecolor_legend(
    image_dir:       Path,
    scale_top:       float,
    scale_divisions: int,
    workers:         int,
    palette:         str = DEFAULT_FALSECOLOR_PALETTE,
) -> None:
    """Generate the standalone falsecolour legend PNG if missing."""
    legend_png  = image_dir / "df_false_legend.png"
    if legend_png.exists():
        return

    legend_tiff = image_dir / "df_false_legend.tiff"
    lt = legend_tiff.as_posix()
    cmd = (
        f'pcomb -e "ro=1;go=1;bo=1" -x 1 -y 1 | '
        f'falsecolor -s {scale_top} -n {scale_divisions} -pal {palette} -l "DF %" '
        f'-lw 400 -lh 1600 | ra_tiff - {lt}'
    )
    utils.execute_new_radiance_commands(cmd, number_of_workers=workers)

    if legend_tiff.exists() and legend_tiff.stat().st_size >= 1000:
        Image.open(legend_tiff).save(legend_png, format="PNG", optimize=True, compress_level=9)
        legend_tiff.unlink()


def _generate_contour_legend(
    image_dir:       Path,
    scale_top:       float,
    scale_divisions: int,
    workers:         int,
) -> None:
    """Generate the standalone contour legend PNG if missing."""
    legend_png  = image_dir / "df_cntr_legend.png"
    if legend_png.exists():
        return

    legend_tiff = image_dir / "df_cntr_legend.tiff"
    lt = legend_tiff.as_posix()
    cmd = (
        f'pcomb -e "ro=1;go=1;bo=1" -x 1 -y 1 | '
        f'falsecolor -cl -s {scale_top} -n {scale_divisions} -l "DF %" '
        f'-lw 400 -lh 1600 | ra_tiff - {lt}'
    )
    utils.execute_new_radiance_commands(cmd, number_of_workers=workers)

    if legend_tiff.exists() and legend_tiff.stat().st_size >= 1000:
        Image.open(legend_tiff).save(legend_png, format="PNG", optimize=True, compress_level=9)
        legend_tiff.unlink()
