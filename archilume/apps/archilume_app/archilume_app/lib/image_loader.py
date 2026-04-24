"""Image loading, tone-mapping, and caching for HDR/TIFF/PDF files."""

import base64
import hashlib
import io
import os
import subprocess
import struct
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Optional

import numpy as np
import pymupdf as fitz
from PIL import Image

_image_cache: OrderedDict[str, str] = OrderedDict()
_cache_lock = threading.Lock()
_CACHE_MAX = 60

# Per-process counter so concurrent rasterize calls for the same (page, dpi)
# never share a .tmp path. Windows denies a second open() on a file already
# open for write, so a shared tmp name causes PermissionError races and
# orphaned .tmp artifacts.
_tmp_counter_lock = threading.Lock()
_tmp_counter = 0


def _unique_tmp_suffix() -> str:
    global _tmp_counter
    with _tmp_counter_lock:
        _tmp_counter += 1
        return f"{os.getpid()}_{_tmp_counter}"


def load_image_as_base64(path: Path) -> Optional[str]:
    """Load an HDR, PIC, or TIFF image and return as a base64-encoded PNG data URI.

    Uses caching (LRU, max 15 entries).
    """
    key = str(path)
    with _cache_lock:
        if key in _image_cache:
            _image_cache.move_to_end(key)
            return _image_cache[key]

    b64 = _load_and_encode(path)
    if b64 is None:
        return None

    with _cache_lock:
        _image_cache[key] = b64
        while len(_image_cache) > _CACHE_MAX:
            _image_cache.popitem(last=False)

    return b64


def _load_and_encode(path: Path) -> Optional[str]:
    """Load image file, tone-map if HDR, return base64 data URI."""
    if not path.exists():
        return None

    suffix = path.suffix.lower()
    try:
        if suffix in (".hdr", ".pic"):
            arr = _load_hdr(path)
        elif suffix in (".tif", ".tiff", ".png", ".jpg", ".jpeg"):
            img = Image.open(path).convert("RGB")
            arr = np.array(img, dtype=np.float32) / 255.0
        else:
            return None
    except Exception:
        return None

    if arr is None:
        return None

    # Convert float32 [0,1] to uint8 PNG
    arr_uint8 = (np.clip(arr, 0.0, 1.0) * 255).astype(np.uint8)
    img = Image.fromarray(arr_uint8, "RGB")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _load_hdr(path: Path) -> Optional[np.ndarray]:
    """Load Radiance HDR/PIC file using pvalue, with fallback to manual parser."""
    arr = _load_hdr_pvalue(path)
    if arr is None:
        arr = _load_hdr_manual(path)
    return arr


def _load_hdr_pvalue(path: Path) -> Optional[np.ndarray]:
    """Load HDR via Radiance pvalue tool."""
    try:
        from archilume import config
        pvalue = config.RADIANCE_BIN_PATH / "pvalue"
        if not pvalue.exists() and not pvalue.with_suffix(".exe").exists():
            return None
    except ImportError:
        return None

    try:
        result = subprocess.run(
            [str(pvalue), "-h", "-H", "-df", str(path)],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None

        # Read header to get dimensions
        width, height = _read_hdr_dimensions(path)
        if width <= 0 or height <= 0:
            return None

        data = np.frombuffer(result.stdout, dtype=np.float32)
        expected = height * width * 3
        if data.size < expected:
            return None

        arr = data[:expected].reshape(height, width, 3)
        return _tonemap(arr)
    except Exception:
        return None


def _load_hdr_manual(path: Path) -> Optional[np.ndarray]:
    """Fallback HDR loader: parse RGBE format manually."""
    try:
        with open(path, "rb") as f:
            # Skip header lines until empty line
            while True:
                line = f.readline()
                if not line or line.strip() == b"":
                    break

            # Read resolution line
            res_line = f.readline().decode("ascii", errors="replace").strip()
            parts = res_line.split()
            if len(parts) != 4:
                return None

            height = int(parts[1])
            width = int(parts[3])
            if width <= 0 or height <= 0:
                return None

            # Read RGBE pixel data
            img = np.zeros((height, width, 3), dtype=np.float32)
            for y in range(height):
                scanline = _read_hdr_scanline(f, width)
                if scanline is None:
                    return None
                img[y] = scanline

        return _tonemap(img)
    except Exception:
        return None


def _read_hdr_scanline(f, width: int) -> Optional[np.ndarray]:
    """Read a single HDR scanline (handles RLE and uncompressed)."""
    header = f.read(4)
    if len(header) < 4:
        return None

    if header[0] == 2 and header[1] == 2:
        # New-style RLE
        scan_width = (header[2] << 8) | header[3]
        if scan_width != width:
            return None

        rgbe = np.zeros((width, 4), dtype=np.uint8)
        for ch in range(4):
            ptr = 0
            while ptr < width:
                byte = f.read(1)
                if not byte:
                    return None
                count = byte[0]
                if count > 128:
                    count -= 128
                    val = f.read(1)
                    if not val:
                        return None
                    rgbe[ptr : ptr + count, ch] = val[0]
                else:
                    data = f.read(count)
                    if len(data) < count:
                        return None
                    rgbe[ptr : ptr + count, ch] = list(data)
                ptr += count
    else:
        # Uncompressed
        rest = f.read((width - 1) * 4)
        raw = header + rest
        if len(raw) < width * 4:
            return None
        rgbe = np.frombuffer(raw, dtype=np.uint8).reshape(width, 4)

    # Convert RGBE to float RGB
    result = np.zeros((width, 3), dtype=np.float32)
    mask = rgbe[:, 3] > 0
    if np.any(mask):
        exp = rgbe[mask, 3].astype(np.float32) - 128.0 - 8.0
        scale = np.ldexp(1.0, exp.astype(int))
        result[mask, 0] = rgbe[mask, 0] * scale
        result[mask, 1] = rgbe[mask, 1] * scale
        result[mask, 2] = rgbe[mask, 2] * scale

    return result


def _tonemap(arr: np.ndarray) -> np.ndarray:
    """Tone-map float32 HDR image to [0, 1] using percentile normalization + gamma."""
    p99 = np.percentile(arr[arr > 0], 99) if np.any(arr > 0) else 1.0
    if p99 > 0:
        arr = arr / p99
    arr = np.clip(arr, 0.0, 1.0)
    arr = np.power(arr, 1.0 / 2.2)
    return arr


def _read_hdr_dimensions(path: Path) -> tuple[int, int]:
    """Read width and height from HDR file header."""
    try:
        with open(path, "rb") as f:
            while True:
                line = f.readline()
                if not line or line.strip() == b"":
                    break
            res_line = f.readline().decode("ascii", errors="replace").strip()
            parts = res_line.split()
            if len(parts) == 4:
                return (int(parts[3]), int(parts[1]))
    except Exception:
        pass
    return (0, 0)


_hdr_params_cache: dict[str, tuple[float, object]] = {}  # path -> (mtime, result)


def read_hdr_view_params(path: Path) -> tuple[float, float, float, float, int, int] | None:
    """Extract (vp_x, vp_y, vh, vv, img_w, img_h) from a Radiance HDR file's VIEW= header.

    Reads all header lines up to the blank separator line (same approach as the
    matplotlib editor's _read_view_params). Returns None if VIEW= is missing or
    incomplete. img_w / img_h come from the resolution string in the same file.

    Results are cached by file path + mtime so repeated calls (e.g. after a
    project switch) only need a stat() rather than a full file open+read.
    """
    key = str(path)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    cached = _hdr_params_cache.get(key)
    if cached is not None and cached[0] == mtime:
        return cached[1]

    result = _read_hdr_view_params_uncached(path)
    _hdr_params_cache[key] = (mtime, result)
    return result


def _read_hdr_view_params_uncached(path: Path) -> tuple[float, float, float, float, int, int] | None:
    import re
    view_line: str | None = None
    try:
        with open(path, "rb") as f:
            for _ in range(500):
                raw = f.readline()
                if not raw or raw.strip() == b"":
                    break
                line = raw.decode("ascii", errors="replace")
                if line.startswith("VIEW="):
                    view_line = line
        if not view_line:
            return None
        vp = re.search(r"-vp\s+([-\d.]+)\s+([-\d.]+)", view_line)
        vh = re.search(r"-vh\s+([-\d.]+)", view_line)
        vv = re.search(r"-vv\s+([-\d.]+)", view_line)
        if not (vp and vh and vv):
            return None
        img_w, img_h = _read_hdr_dimensions(path)
        return (float(vp.group(1)), float(vp.group(2)),
                float(vh.group(1)), float(vv.group(1)),
                img_w, img_h)
    except Exception:
        pass
    return None


def get_image_dimensions(path: Path) -> tuple[int, int]:
    """Get (width, height) of an image file without fully loading it."""
    suffix = path.suffix.lower()
    if suffix in (".hdr", ".pic"):
        return _read_hdr_dimensions(path)
    try:
        with Image.open(path) as img:
            return img.size
    except Exception:
        return (0, 0)


_scan_hdr_files_cache: dict[str, tuple[float, list[dict]]] = {}  # dir -> (mtime, result)


def scan_hdr_files(image_dir: Path) -> list[dict]:
    """Scan directory for HDR/PIC files and their associated TIFF/PNG variants.

    Returns list of dicts: {hdr_path, tiff_paths, name, suffix}.

    Uses a single ``os.scandir()`` pass instead of multiple ``glob()`` calls
    to minimise filesystem round-trips (critical for Docker bind-mounts on
    Windows where each syscall adds ~5-50 ms latency). Results are cached by
    directory mtime so repeated project opens skip the scan entirely until a
    file is added, removed, or renamed inside *image_dir*.
    """
    if not image_dir.exists():
        return []

    key = str(image_dir)
    try:
        dir_mtime = image_dir.stat().st_mtime
    except OSError:
        dir_mtime = 0.0
    cached = _scan_hdr_files_cache.get(key)
    if cached is not None and cached[0] == dir_mtime:
        return cached[1]

    # Single directory scan — collect all files in one syscall
    all_files: dict[str, Path] = {}
    try:
        with os.scandir(image_dir) as it:
            for entry in it:
                if entry.is_file(follow_symlinks=False):
                    all_files[entry.name] = Path(entry.path)
    except OSError:
        return []

    # Build legend map from collected entries
    legend_map: dict[str, str] = {}
    for name, fpath in all_files.items():
        if name.endswith("_legend.png"):
            key = name.removesuffix("_legend.png")
            legend_map[key] = str(fpath)

    # Separate HDR/PIC files and variant files
    hdr_files: list[Path] = sorted(
        (p for n, p in all_files.items() if n.lower().endswith((".hdr", ".pic"))),
        key=lambda p: p.stem.lower(),
    )
    variant_files: list[Path] = [
        p for n, p in all_files.items()
        if n.lower().endswith((".tif", ".tiff", ".png"))
        and "_aoi_overlay" not in n
        and "_aoi_annotated" not in n
        and not n.endswith("_legend.png")
    ]

    result = []
    for hdr_path in hdr_files:
        stem = hdr_path.stem
        prefix = stem + "_"
        tiff_paths = sorted(
            (p for p in variant_files if p.stem.startswith(prefix)),
            key=lambda p: p.stem,
        )
        result.append({
            "hdr_path": str(hdr_path),
            "tiff_paths": [str(p) for p in tiff_paths],
            "name": stem,
            "suffix": hdr_path.suffix,
            "legend_map": legend_map,
        })

    _scan_hdr_files_cache[key] = (dir_mtime, result)
    return result


def _pdf_fingerprint(pdf_path: Path) -> str:
    """md5 of (resolved path | size | mtime_ns), 10 hex chars.

    Stat-only — microseconds to compute. Invalidates cache when the PDF is
    replaced, edited, or moved. Raises OSError if the file is missing.
    """
    st = pdf_path.stat()
    key = f"{pdf_path.resolve()}|{st.st_size}|{st.st_mtime_ns}"
    return hashlib.md5(key.encode()).hexdigest()[:10]


def _overlay_cache_path(
    pdf_path: Path, page_index: int, dpi: int, cache_dir: Path,
) -> Path:
    """Resolve the .png cache path for (pdf, page, dpi). Creates cache_dir.

    Filename encodes the PDF fingerprint so edits/replacements at the same
    path produce fresh cache entries (old entries remain orphaned).
    """
    fp = _pdf_fingerprint(pdf_path)
    fname = f"{pdf_path.stem}_p{page_index}_{dpi}dpi_{fp}.png"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / fname


def rasterize_pdf_page(
    pdf_path: Path, page_index: int = 0, dpi: int = 150,
    cache_dir: Optional[Path] = None,
) -> tuple[Optional[Path], int, int]:
    """Rasterize a PDF page and return (cache_path, width, height).

    Caches the rendered page as a deflated PNG under *cache_dir* keyed by
    (stem, page, dpi, content fingerprint). The caller builds the served
    URL from the returned Path — image_loader is agnostic of URL shape
    or project layout.

    Returns (None, 0, 0) when the PDF is missing, the page index is out of
    range, or *cache_dir* is not supplied.
    """
    if not pdf_path.exists() or cache_dir is None:
        return None, 0, 0

    try:
        cache_path = _overlay_cache_path(pdf_path, page_index, dpi, cache_dir)
    except OSError:
        return None, 0, 0

    if cache_path.exists():
        try:
            with Image.open(cache_path) as img:
                w, h = img.size
            return cache_path, w, h
        except Exception:
            pass  # fall through to re-rasterize a corrupt cache entry

    tmp_path = cache_path.with_suffix(f".tmp_{_unique_tmp_suffix()}.png")
    try:
        doc = fitz.open(str(pdf_path))
        if page_index >= len(doc):
            doc.close()
            return None, 0, 0

        page = doc[page_index]
        scale = dpi / 72.0
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        img_w, img_h = pix.width, pix.height
        doc.close()

        img.save(tmp_path, format="PNG", optimize=True)
        tmp_path.replace(cache_path)
        return cache_path, img_w, img_h
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return None, 0, 0


def rasterize_pdf_page_to_cache(
    pdf_path: Path, page_index: int, dpi: int, cache_dir: Path,
) -> bool:
    """Rasterize a PDF page to the PNG disk cache only (no URL return).

    For background prefetch: skip if cache already exists, otherwise rasterise
    via PyMuPDF and atomically write a deflated PNG. Returns True if the PNG
    exists after the call, False on any failure.
    """
    if not pdf_path.exists():
        return False
    try:
        cache_path = _overlay_cache_path(pdf_path, page_index, dpi, cache_dir)
    except OSError:
        return False

    if cache_path.exists():
        return True

    tmp_path = cache_path.with_suffix(f".tmp_{_unique_tmp_suffix()}.png")
    try:
        doc = fitz.open(str(pdf_path))
        if page_index >= len(doc):
            doc.close()
            return False
        page = doc[page_index]
        scale = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        doc.close()

        img.save(tmp_path, format="PNG", optimize=True)
        tmp_path.replace(cache_path)
        return True
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def get_pdf_page_count(pdf_path: Path) -> int:
    """Return number of pages in a PDF."""
    try:
        doc = fitz.open(str(pdf_path))
        count = len(doc)
        doc.close()
        return count
    except Exception:
        return 0


def clear_cache() -> None:
    """Clear every project-scoped module cache (images, HDR params, dir scans, view groups).

    Called from ``EditorState.init_on_load`` on every boot / project-switch reload so
    path-keyed cache entries from a previous project can't collide with a new one.
    """
    with _cache_lock:
        _image_cache.clear()
    _hdr_params_cache.clear()
    _scan_hdr_files_cache.clear()
    _view_groups_cache.clear()


# ---------------------------------------------------------------------------
# Sunlight view grouping (timeseries HDR frames per level)
# ---------------------------------------------------------------------------

_view_groups_cache: dict[str, tuple[float, list[dict]]] = {}


def _extract_view_name(
    hdr_stem: str,
    sky_stems: list[str],
    overcast_sky_stem: str = "",
) -> tuple[str, str]:
    """Return (view_prefix, sky_name) by stripping the longest matching sky suffix.

    view_prefix is everything up to and excluding the trailing _{sky_name}.
    Falls back to (hdr_stem, "") when no sky suffix matches — caller treats the
    HDR as its own single-frame group.

    The SunlightRenderer names the overcast baseline with a *double* underscore
    (``{octree}_{view}__{overcast_sky_stem}``) so it can be distinguished from
    the single-underscore timestep frames. When the matched sky is the
    overcast, strip that extra underscore so the returned view_prefix lines up
    with the sunlight-frame prefix for the same view.
    """
    for sky in sorted(sky_stems, key=len, reverse=True):
        suffix = f"_{sky}"
        if hdr_stem.endswith(suffix):
            prefix = hdr_stem[: -len(suffix)]
            if overcast_sky_stem and sky == overcast_sky_stem and prefix.endswith("_"):
                prefix = prefix[:-1]
            return prefix, sky
    return hdr_stem, ""


def scan_sunlight_view_groups(
    image_dir: Path,
    sky_stems: list[str],
    overcast_sky_stem: str = "",
) -> list[dict]:
    """Group HDRs in *image_dir* by view, using sky stems to identify the
    timestep suffix of each filename.

    Returns a list (sorted by view name) of dicts shaped:
        {
            "view_name": str,              # trimmed of the common octree prefix
            "view_prefix": str,
            "frames": [
                {"hdr_path": str, "png_path": str, "sky_name": str,
                 "hdr_stem": str, "frame_label": str},
                ...
            ],
            "underlay_png_path": str,      # "" when overcast not rendered
            "underlay_hdr_stem": str,      # "" when overcast not rendered
        }

    ``png_path`` points at the ``{hdr_stem}.png`` sibling written by the
    SunlightRenderer.sun_only_rendering_pipeline. The app expects the PNG to
    already exist — there is no on-demand tone-mapping fallback.

    When ``overcast_sky_stem`` is supplied and matches a frame's sky name, that
    frame is pulled out of ``frames`` and attached to the view group as the
    underlay baseline instead. Absent overcast → ``underlay_png_path == ""``.

    When *sky_stems* is empty, each HDR becomes its own single-frame group so
    the UI still works for markup-only projects that lack a sky directory.
    """
    if not image_dir.exists():
        return []
    hdr_infos = scan_hdr_files(image_dir)
    if not hdr_infos:
        return []

    key = f"{image_dir}|{'|'.join(sorted(sky_stems))}|{overcast_sky_stem}"
    try:
        dir_mtime = image_dir.stat().st_mtime
    except OSError:
        dir_mtime = 0.0
    cached = _view_groups_cache.get(key)
    if cached is not None and cached[0] == dir_mtime:
        return cached[1]

    groups: dict[str, list[dict]] = {}
    underlays: dict[str, dict] = {}
    for info in hdr_infos:
        hdr_stem = info["name"]
        hdr_path = Path(info["hdr_path"])
        view_prefix, sky_name = _extract_view_name(hdr_stem, sky_stems, overcast_sky_stem)
        png_path = hdr_path.parent / f"{hdr_stem}.png"
        if overcast_sky_stem and sky_name == overcast_sky_stem:
            underlays[view_prefix] = {
                "png_path": str(png_path),
                "hdr_stem": hdr_stem,
            }
            groups.setdefault(view_prefix, [])
            continue
        frame = {
            "hdr_path": str(hdr_path),
            "png_path": str(png_path),
            "sky_name": sky_name,
            "hdr_stem": hdr_stem,
            "frame_label": sky_name or hdr_stem,
        }
        groups.setdefault(view_prefix, []).append(frame)

    # Trim the shared ``{octree_base}_`` prefix from the displayed view name,
    # but only at an underscore boundary so sibling views like "level1" and
    # "level2" don't collapse to "1" / "2". If the remaining token is
    # digits-only (e.g. ``090000``) roll the cut back one more segment so the
    # qualifier (e.g. ``ffl_``) rides along and the label reads ``ffl_090000``.
    # Skip trimming entirely when it would produce a name shorter than 2
    # chars (markup projects with no sky files).
    common_prefix = ""
    if sky_stems and len(groups) > 1:
        raw = _longest_common_prefix(list(groups.keys()))
        cut = raw.rfind("_")
        candidate = raw[: cut + 1] if cut >= 0 else ""
        if candidate:
            # If the distinguishing tail is digits-only, include the prior
            # qualifier token (e.g. ``ffl``) by rolling the cut back once.
            tails = [k[len(candidate):] for k in groups.keys()]
            if tails and all(t.isdigit() for t in tails):
                prev_cut = candidate[:-1].rfind("_")
                candidate = candidate[: prev_cut + 1] if prev_cut >= 0 else ""
        if candidate and all(len(k) - len(candidate) >= 2 for k in groups.keys()):
            common_prefix = candidate

    result: list[dict] = []
    for view_prefix in sorted(groups.keys()):
        frames = sorted(groups[view_prefix], key=lambda f: f["sky_name"] or f["hdr_stem"])
        view_name = view_prefix[len(common_prefix):] if common_prefix else view_prefix
        if not view_name:
            view_name = view_prefix
        underlay = underlays.get(view_prefix, {})
        result.append({
            "view_name": view_name,
            "view_prefix": view_prefix,
            "frames": frames,
            "underlay_png_path": underlay.get("png_path", ""),
            "underlay_hdr_stem": underlay.get("hdr_stem", ""),
        })

    _view_groups_cache[key] = (dir_mtime, result)
    return result


def _longest_common_prefix(strings: list[str]) -> str:
    if not strings:
        return ""
    s1, s2 = min(strings), max(strings)
    i = 0
    while i < len(s1) and i < len(s2) and s1[i] == s2[i]:
        i += 1
    return s1[:i]


def load_frame_png_as_base64(hdr_path: Path) -> Optional[str]:
    """Load a sunlight frame as base64 PNG.

    The SunlightAccessWorkflow writes a `{hdr_stem}.png` sibling next to every
    HDR. Project open runs a preflight that regenerates any missing PNGs. If a
    PNG is still absent here (e.g. a single corrupt output), trigger a one-shot
    HDR→PNG conversion for just this HDR, then load the PNG. The app never
    tone-maps HDR at runtime.
    """
    png_path = hdr_path.parent / f"{hdr_path.stem}.png"
    if png_path.exists() and png_path.stat().st_size > 0:
        return load_image_as_base64(png_path)

    from archilume.post.hdr2png import convert_hdrs_to_pngs
    convert_hdrs_to_pngs([hdr_path])
    if png_path.exists() and png_path.stat().st_size > 0:
        return load_image_as_base64(png_path)
    return None


def regenerate_sunlight_underlay_png(underlay_hdr_path: Path, exposure: float) -> None:
    """Regenerate a sunlight overcast underlay PNG with new exposure setting.

    Converts the HDR to PNG with the specified exposure, then invalidates
    the image cache so the updated PNG is loaded on next access.

    Args:
        underlay_hdr_path: Path to the overcast baseline HDR file
        exposure: f-stop exposure adjustment (-6 to +6)
    """
    if not underlay_hdr_path.exists():
        return

    # Force regeneration by deleting the PNG first
    png_path = underlay_hdr_path.parent / f"{underlay_hdr_path.stem}.png"
    png_path.unlink(missing_ok=True)

    # Regenerate PNG with new exposure
    from archilume.post.hdr2png import convert_hdrs_to_pngs
    convert_hdrs_to_pngs([underlay_hdr_path], exposure=exposure)

    # Invalidate cache for this PNG and TIFF so next load gets fresh data
    with _cache_lock:
        for key in [str(png_path), str(underlay_hdr_path.with_suffix(".tiff"))]:
            _image_cache.pop(key, None)
