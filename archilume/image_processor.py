"""Image processing for Radiance rendered outputs."""

from archilume import utils
from dataclasses import dataclass, field
from typing import List
from pathlib import Path
from datetime import datetime
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont
import re

@dataclass
class ImageProcessor:
    """Post-processes rendered TIFF images with metadata annotations, AOI overlays, and animations."""

    skyless_octree_path: Path
    overcast_sky_file_path: Path
    sky_files_dir: Path
    view_files_dir: Path
    image_dir: Path
    x_res: int
    y_res: int
    latitude: float
    sky_files: List[Path] = field(default_factory=list, init=False)
    view_files: List[Path] = field(default_factory=list, init=False)

    def __post_init__(self):
        """Auto-populate file lists and validate resolution."""
        self.sky_files = sorted(self.sky_files_dir.glob('*.sky'))
        self.view_files = sorted(self.view_files_dir.glob('*.vp'))
        if self.x_res <= 0 or self.y_res <= 0:
            raise ValueError(f"Resolution must be positive: x_res={self.x_res}, y_res={self.y_res}")

    def sepp65_results_pipeline(self):
        """Process rendered images: stamp with metadata/AOI, create animations and grids."""
        tiff_files = list(self.image_dir.glob('*_combined.tiff'))

        _stamp_tiff_files_with_datetime_loc(tiff_files, self.latitude, font_size=24,
                                            text_color=(255, 255, 255), background_alpha=180, number_of_workers=10)
        _stamp_tiff_files_with_aoi(tiff_files, lineweight=1, font_size=32,
                                   text_color=(255, 0, 0), background_alpha=180, number_of_workers=10)

        utils.combine_tiffs_by_view(self.image_dir, self.view_files, output_format='gif', number_of_workers=8)
        utils.combine_tiffs_by_view(self.image_dir, self.view_files, output_format='mp4', number_of_workers=8)

        utils.create_grid_mp4(list(self.image_dir.glob('animated_results_*.mp4')),
                             self.image_dir, grid_size=(3, 2), target_size=(2048, 2048), fps=2)
        utils.create_grid_gif(list(self.image_dir.glob('animated_results_*.gif')),
                             self.image_dir, grid_size=(3, 2), target_size=(2048, 2048), fps=2)

        print("\nRendering sequence completed successfully.\n")

def _load_font(font_size: int) -> ImageFont.FreeTypeFont:
    """Load Arial font or fallback to default."""
    try:
        return ImageFont.truetype("arial.ttf", font_size)
    except (OSError, IOError):
        return ImageFont.load_default()

def _process_parallel(items: list, worker_func, num_workers: int):
    """Execute worker function on items in parallel or sequentially."""
    if num_workers == 1:
        for item in items:
            print(worker_func(item))
    else:
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            for future in concurrent.futures.as_completed([executor.submit(worker_func, item) for item in items]):
                print(future.result())

def _stamp_tiff_files_with_datetime_loc(tiff_paths: list[Path], latitude: float, font_size: int = 24,
                             text_color: tuple = (255, 255, 0), background_alpha: int = 0,
                             padding: int = 10, number_of_workers: int = 4) -> None:
    """Stamp TIFF files with location/datetime info."""
    if not tiff_paths:
        return

    def _stamp(tiff_path: Path) -> str:
        try:
            if not tiff_path.exists():
                return f"File not found: {tiff_path.name}"

            filename = tiff_path.stem
            current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M")
            level, timestep = "Unknown", "Unknown"

            if ts := re.search(r'(\d{4}_\d{4})', filename):
                ts_str = ts.group(1)
                months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                timestep = f"{months[int(ts_str[:2])-1]} {int(ts_str[2:4])} {ts_str[5:7]}:{ts_str[7:9]}"

            if level_match := re.search(r'[_]?L(\d+)', filename):
                level = f"L{level_match.group(1)}"

            text = f"Created: {current_datetime}, Level: {level}, Timestep: {timestep}, Location: lat: {latitude}"

            image = Image.open(tiff_path).convert('RGBA')
            draw = ImageDraw.Draw(image)
            font = _load_font(font_size)

            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            x, y = image.width - tw - padding, image.height - th - padding

            if background_alpha > 0:
                draw.rectangle([x - padding//2, y - padding//2, x + tw + padding//2, y + th + padding//2],
                              fill=(0, 0, 0, background_alpha))

            draw.text((x, y), text, font=font, fill=text_color + (255,))
            image.save(tiff_path, format='TIFF')
            return f"Stamped {tiff_path.name}"
        except Exception as e:
            return f"Error: {tiff_path.name}: {e}"

    print(f"Stamping {len(tiff_paths)} files with {number_of_workers} workers")
    _process_parallel(tiff_paths, _stamp, number_of_workers)
    print(f"Completed {len(tiff_paths)} files")

def _stamp_tiff_files_with_aoi(tiff_paths: list[Path], lineweight: int = 5, font_size: int = 32,
                              text_color: tuple = (255, 0, 0), background_alpha: int = 180,
                              number_of_workers: int = 10) -> None:
    """Stamp TIFF files with AOI polygons and room labels."""

    def _parse_aoi_file(aoi_path: Path) -> dict | None:
        try:
            with open(aoi_path, 'r') as f:
                lines = [line.strip() for line in f.readlines()]

            perimeter_pixels = [(int(parts[2]), int(parts[3]))
                               for line in lines[5:] if line and ' ' in line
                               if (parts := line.split()) and len(parts) >= 4]

            central_pixel = (sum(p[0] for p in perimeter_pixels) // len(perimeter_pixels),
                            sum(p[1] for p in perimeter_pixels) // len(perimeter_pixels)) if perimeter_pixels else None

            return {
                'apartment_room': lines[0].replace("AOI Points File: ", ""),
                'view_file': lines[1].replace("ASSOCIATED VIEW FILE: ", ""),
                'z_height': float(lines[2].replace("FFL z height(m): ", "")),
                'central_pixel': central_pixel,
                'perimeter_pixels': perimeter_pixels
            }
        except Exception as e:
            print(f"Error parsing {aoi_path}: {e}")
            return None

    aoi_dir = Path(__file__).parent.parent / "outputs" / "aoi"
    aoi_files = list(aoi_dir.glob("*.aoi")) if aoi_dir.exists() else []

    if not tiff_paths or not aoi_files:
        print("AOI stamping skipped - missing files")
        return

    def _stamp(tiff_path: Path) -> str:
        try:
            if not tiff_path.exists():
                return f"Not found: {tiff_path.name}"

            if not (match := re.search(r'plan_L\d+', tiff_path.stem)):
                return f"No view match: {tiff_path.name}"

            view_file = f"{match.group(0)}.vp"
            matching_aois = [aoi for aoi_file in aoi_files
                            if (aoi := _parse_aoi_file(aoi_file)) and aoi['view_file'] == view_file]

            if not matching_aois:
                return f"No AOI for {view_file}: {tiff_path.name}"

            image = Image.open(tiff_path).convert('RGBA')
            draw = ImageDraw.Draw(image)
            font = _load_font(font_size)
            rooms = 0

            for aoi in matching_aois:
                if len(aoi['perimeter_pixels']) < 3:
                    continue

                polygon = aoi['perimeter_pixels'] + [aoi['perimeter_pixels'][0]]
                for i in range(len(polygon) - 1):
                    draw.line([polygon[i], polygon[i + 1]], fill=text_color, width=lineweight)

                if cp := aoi['central_pixel']:
                    label = aoi['apartment_room']
                    bbox = draw.textbbox((0, 0), label, font=font)
                    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                    lx, ly = cp[0] - tw // 2, cp[1] - th // 2

                    if background_alpha > 0:
                        draw.rectangle([lx - 5, ly - 5, lx + tw + 5, ly + th + 5],
                                      fill=(0, 0, 0, background_alpha))
                    draw.text((lx, ly), label, font=font, fill=text_color + (255,))
                    rooms += 1

            image.save(tiff_path, format='TIFF')
            return f"Stamped {tiff_path.name}: {rooms} rooms"
        except Exception as e:
            return f"Error {tiff_path.name}: {e}"

    print(f"Stamping {len(tiff_paths)} files with AOI using {number_of_workers} workers")
    _process_parallel(tiff_paths, _stamp, number_of_workers)
    print(f"Completed AOI stamping")



