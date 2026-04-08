"""Image loading, tone-mapping, and caching for HDR/TIFF/PDF files."""

import base64
import hashlib
import io
import subprocess
import struct
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

_image_cache: OrderedDict[str, str] = OrderedDict()
_cache_lock = threading.Lock()
_CACHE_MAX = 15


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


def read_hdr_view_params(path: Path) -> tuple[float, float, float, float] | None:
    """Extract (vp_x, vp_y, vh, vv) from a Radiance HDR file's VIEW= header line.

    Returns None if the VIEW line is missing or incomplete.
    """
    import re
    try:
        with open(path, "rb") as f:
            for _ in range(50):
                raw = f.readline()
                if not raw or raw.strip() == b"":
                    break
                line = raw.decode("ascii", errors="replace")
                if not line.startswith("VIEW="):
                    continue
                vp = re.search(r"-vp\s+([-\d.]+)\s+([-\d.]+)", line)
                vh = re.search(r"-vh\s+([-\d.]+)", line)
                vv = re.search(r"-vv\s+([-\d.]+)", line)
                if vp and vh and vv:
                    return (float(vp.group(1)), float(vp.group(2)),
                            float(vh.group(1)), float(vv.group(1)))
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


def scan_hdr_files(image_dir: Path) -> list[dict]:
    """Scan directory for HDR/PIC files and their associated TIFF/PNG variants.

    Returns list of dicts: {hdr_path, tiff_paths, name, suffix}.
    """
    if not image_dir.exists():
        return []

    hdr_files = []
    for ext in ("*.hdr", "*.pic"):
        hdr_files.extend(image_dir.glob(ext))
    hdr_files.sort(key=lambda p: p.stem.lower())

    result = []
    for hdr_path in hdr_files:
        stem = hdr_path.stem
        tiff_paths = []
        for tiff_ext in ("*.tif", "*.tiff", "*.png"):
            for tp in image_dir.glob(tiff_ext):
                if tp.stem.startswith(stem + "_") and "_aoi_overlay" not in tp.stem:
                    tiff_paths.append(tp)
        tiff_paths.sort(key=lambda p: p.stem)

        result.append({
            "hdr_path": str(hdr_path),
            "tiff_paths": [str(p) for p in tiff_paths],
            "name": stem,
            "suffix": hdr_path.suffix,
        })

    return result


def rasterize_pdf_page(
    pdf_path: Path, page_index: int = 0, dpi: int = 150,
    cache_dir: Optional[Path] = None,
) -> tuple[Optional[str], int, int]:
    """Rasterize a PDF page to a base64-encoded PNG data URI.

    Uses PyMuPDF (fitz) for rasterization. If *cache_dir* is provided the
    rasterized image is saved as a .npy file there (keyed by PDF stem, page,
    DPI, and a hash of the resolved PDF path) so subsequent calls for the same
    page/DPI are instant.
    """
    try:
        import fitz
    except ImportError:
        return None, 0, 0

    if not pdf_path.exists():
        return None, 0, 0

    # --- disk cache lookup ---------------------------------------------------
    cache_path: Optional[Path] = None
    if cache_dir is not None:
        pdf_hash = hashlib.md5(str(pdf_path.resolve()).encode()).hexdigest()[:6]
        fname = f"{pdf_path.stem}_p{page_index}_{dpi}dpi_{pdf_hash}.npy"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / fname
        if cache_path.exists():
            try:
                arr = np.load(str(cache_path))
                h, w = arr.shape[:2]
                img = Image.fromarray(arr)
                buf = io.BytesIO()
                img.save(buf, format="PNG", optimize=False)
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                return f"data:image/png;base64,{b64}", w, h
            except Exception:
                pass  # fall through to re-rasterize

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

        # --- write disk cache ------------------------------------------------
        if cache_path is not None:
            try:
                tmp_path = cache_path.with_suffix(".tmp.npy")
                np.save(str(tmp_path), np.array(img))
                tmp_path.replace(cache_path)
            except Exception:
                pass

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=False)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}", img_w, img_h
    except Exception:
        return None, 0, 0


def get_pdf_page_count(pdf_path: Path) -> int:
    """Return number of pages in a PDF."""
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        count = len(doc)
        doc.close()
        return count
    except Exception:
        return 0


def clear_cache() -> None:
    """Clear the image cache."""
    with _cache_lock:
        _image_cache.clear()
