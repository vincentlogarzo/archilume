"""HDR to Falsecolour and Contour PNG converter.

Converts a rendered HDR image into two post-processed PNG outputs:
  - Falsecolour image  (*_df_false.png)  — spectral palette scaled to DF range
  - Contour overlay    (*_df_cntr.png)   — contour lines composited over a dimmed HDR

Standalone legend PNGs are also generated on the first call (guarded by existence
check so they are not regenerated for every HDR in a batch).
"""

# Archilume imports
from archilume import utils

# Standard library imports
from pathlib import Path
import logging

# Third-party imports
from PIL import Image

logger = logging.getLogger(__name__)


def hdr2png_falsecolour(
    hdr_path:   Path,
    image_dir:  Path,
    scale:      float = 4.0,
    n_levels:   int   = 20,
    workers:    int   = 1,
) -> None:
    """Generate falsecolour and contour overlay PNGs for a single HDR.

    Legend PNGs are written to *image_dir* on the first call and skipped on
    subsequent calls (existence-guarded), so this function is safe to call in
    a loop over many HDR files.

    Args:
        hdr_path:   Path to the source HDR file.
        image_dir:  Directory where all output files are written.
        scale:      Maximum DF value for the falsecolour scale (default 4 -> 4 % DF).
        n_levels:   Number of falsecolour / contour levels (default 20).
        workers:    Number of parallel workers for Radiance commands (default 1).
    """
    stem = hdr_path.stem
    d    = image_dir

    dimmed       = d / f"{stem}_dimmed_temp.hdr"
    contour_hdr  = d / f"{stem}_df_cntr.hdr"
    contour_tiff = d / f"{stem}_df_cntr.tiff"
    false_tiff   = d / f"{stem}_df_false.tiff"

    # Use POSIX paths (forward slashes) for Radiance CLI compatibility on Windows
    src  = hdr_path.as_posix()
    ft   = false_tiff.as_posix()
    ch   = contour_hdr.as_posix()
    ct   = contour_tiff.as_posix()
    dm   = dimmed.as_posix()

    contour_scale  = scale / 2
    contour_levels = max(1, n_levels // 5)

    cmds = [
        # Falsecolour visualisation
        f'pcomb -s 0.01 {src} | falsecolor -s {scale} -n {n_levels} -pal spec -l "DF %" -lw 0 | ra_tiff - {ft}',

        # Contour HDR
        f'pcomb -s 0.01 {src} | falsecolor -cl -s {contour_scale} -n {contour_levels} -l "DF %" -lw 0 -lh 0 > {ch}',

        # Dimmed background
        f"pfilt -e 0.5 {src} > {dm}",
    ]
    utils.execute_new_radiance_commands(cmds, number_of_workers=workers)

    # Contour composite depends on dimmed + contour_hdr being written first
    composite_cmd = (
        f'pcomb -e "cond=ri(2)+gi(2)+bi(2)" '
        f'-e "ro=if(cond-.01,ri(2),ri(1))" '
        f'-e "go=if(cond-.01,gi(2),gi(1))" '
        f'-e "bo=if(cond-.01,bi(2),bi(1))" '
        f"{dm} {ch} | ra_tiff - {ct}"
    )
    utils.execute_new_radiance_commands(composite_cmd, number_of_workers=workers)

    # Convert TIFFs to PNG
    for tiff in (false_tiff, contour_tiff):
        if tiff.exists() and tiff.stat().st_size >= 1000:
            Image.open(tiff).save(tiff.with_suffix('.png'), format='PNG', optimize=True, compress_level=9)

    # Clean up intermediates
    for tmp in (dimmed, contour_hdr, false_tiff, contour_tiff):
        if tmp.exists():
            tmp.unlink()

    # Generate legends once (existence-guarded inside)
    _generate_legends(image_dir, scale, n_levels, workers)


def _generate_legends(
    image_dir: Path,
    scale:     float = 4.0,
    n_levels:  int   = 20,
    workers:   int   = 1,
) -> None:
    """Generate standalone legend PNGs if they do not already exist."""
    legend_false_png = image_dir / 'df_false_legend.png'
    legend_cntr_png  = image_dir / 'df_cntr_legend.png'

    if legend_false_png.exists() and legend_cntr_png.exists():
        return

    contour_scale  = scale / 2
    contour_levels = max(1, n_levels // 5)

    legend_false_tiff = image_dir / 'df_false_legend.tiff'
    legend_cntr_tiff  = image_dir / 'df_cntr_legend.tiff'

    lft = legend_false_tiff.as_posix()
    lct = legend_cntr_tiff.as_posix()

    cmds = [
        f'pcomb -e "ro=1;go=1;bo=1" -x 1 -y 1 | falsecolor -s {scale} -n {n_levels} -pal spec -l "DF %" -lw 400 -lh 1600 | ra_tiff - {lft}',
        f'pcomb -e "ro=1;go=1;bo=1" -x 1 -y 1 | falsecolor -cl -s {contour_scale} -n {contour_levels} -l "DF %" -lw 400 -lh 1600 | ra_tiff - {lct}',
    ]
    utils.execute_new_radiance_commands(cmds, number_of_workers=workers)

    for tiff, png in ((legend_false_tiff, legend_false_png), (legend_cntr_tiff, legend_cntr_png)):
        if tiff.exists() and tiff.stat().st_size >= 1000:
            Image.open(tiff).save(png, format='PNG', optimize=True, compress_level=9)
            tiff.unlink()
