# Archilume imports
from archilume import config

# Standard library imports
from dataclasses import dataclass, field
from typing import List
from pathlib import Path
from datetime import datetime
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import cv2
import re

# Third-party imports


# Date formatting constants
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

@dataclass
class Tiff2Animation:
    """Post-processes rendered TIFF images with metadata annotations, AOI overlays, and animations."""

    skyless_octree_path: Path
    overcast_sky_file_path: Path
    x_res: int
    y_res: int
    latitude: float
    ffl_offset: float

    # Optional fields with config defaults
    sky_files_dir: Path = field(default_factory=lambda: config.SKY_DIR)
    view_files_dir: Path = field(default_factory=lambda: config.VIEW_DIR)
    image_dir: Path = field(default_factory=lambda: config.IMAGE_DIR)

    # Auto-populated fields
    sky_files: List[Path] = field(default_factory=list, init=False)
    view_files: List[Path] = field(default_factory=list, init=False)

    def __post_init__(self):
        """Auto-populate file lists and validate resolution."""
        self.sky_files = sorted(self.sky_files_dir.glob('*.sky'))
        self.view_files = sorted(self.view_files_dir.glob('*.vp'))
        if self.x_res <= 0 or self.y_res <= 0:
            raise ValueError(f"Resolution must be positive: x_res={self.x_res}, y_res={self.y_res}")

    def nsw_adg_sunlight_access_results_pipeline(self):
        """Process rendered images: stamp with metadata/AOI, create animations and grids for NSW Apartment Design Guidelines Sunlight access compliance."""
        tiff_files = list(self.image_dir.glob('*_combined.tiff'))

        # Combined stamping: 2x faster by opening/saving each file only once
        _stamp_tiff_files_combined(tiff_files, self.latitude, self.ffl_offset,
                                   metadata_font_size=24, metadata_color=(255, 255, 255), metadata_bg_alpha=180,
                                   aoi_lineweight=2, aoi_font_size=32, aoi_color=(255, 0, 0), aoi_bg_alpha=180,
                                   number_of_workers=config.WORKERS["metadata_stamping"])

        self._combine_tiffs_by_view(output_format='gif', fps=2, number_of_workers=config.WORKERS["gif_animation"])

        print("\nRendering sequence completed successfully.\n")

    def _combine_tiffs_by_view(self, output_format: str = 'gif', fps: int = None, number_of_workers: int = 4) -> None:
        """Create separate animated files grouped by view file names using parallel processing."""

        def _combine_tiffs(tiff_paths: list[Path], output_path: Path, duration_ms: int = 4000, output_format: str = 'gif') -> None:
            """Combine multiple TIFF files into a single animated file. Default duration is 4000ms per frame (0.25 fps)."""
            duration = duration_ms  # Duration in milliseconds per frame
            if output_format.lower() == 'gif':
                tiffs = [Image.open(f) for f in tiff_paths]
                tiffs[0].save(output_path, save_all=True, append_images=tiffs[1:], duration=duration, loop=0)
            elif output_format.lower() == 'mp4':
                first_tiff = Image.open(tiff_paths[0])
                width, height = first_tiff.size
                fps_calc = fps
                fourcc = cv2.VideoWriter_fourcc(*'avc1')
                video_writer = cv2.VideoWriter(str(output_path), fourcc, fps_calc, (width, height))

                if not video_writer.isOpened():
                    raise RuntimeError(f"Failed to create video writer for {output_path}. Check codec availability.")

                for tiff_path in tiff_paths:
                    tiff = Image.open(tiff_path)
                    frame_rgb = tiff.convert('RGB')
                    frame_bgr = cv2.cvtColor(np.array(frame_rgb), cv2.COLOR_RGB2BGR)
                    video_writer.write(frame_bgr)

                video_writer.release()
            else:
                raise ValueError(f"Unsupported output format: {output_format}. Use 'gif' or 'mp4'.")

        tiff_files = [path for path in self.image_dir.glob('*.tiff')]
        tiff_files = [tiff for tiff in tiff_files if not tiff.name.startswith('animated_results_')
                     and tiff.name != 'animated_results_grid_all_levels.tiff']

        if not tiff_files:
            print("No TIFF files found in the image directory (excluding result files).")
            return

        def _process_single_view(view_file: Path) -> str:
            """Process a single view file to create animated output."""
            view_name = view_file.stem
            view_tiff_files = [tiff for tiff in tiff_files if view_name in tiff.name]

            if not view_tiff_files:
                return f"X No TIFF files found for view: {view_name}"

            try:
                num_frames = len(view_tiff_files)

                if fps is None:
                    duration = num_frames * 1000
                    calculated_fps = 1.0
                else:
                    duration = int((num_frames / fps) * 1000)
                    calculated_fps = fps

                per_frame_duration = int(duration / num_frames) if num_frames > 0 else 1000
                output_file_path = self.image_dir / f'animated_results_{view_name}.{output_format.lower()}'

                if output_file_path.exists():
                    output_file_path.unlink()

                _combine_tiffs(view_tiff_files, output_file_path, per_frame_duration, output_format)
                return f"OK Created {output_format.upper()} animation for {view_name}: {num_frames} frames, {duration/1000:.1f}s at {calculated_fps} FPS"
            except Exception as e:
                return f"X Error processing {view_name}: {e}"

        print(f"Processing {len(self.view_files)} views using {number_of_workers} workers")

        if number_of_workers == 1:
            for view_file in self.view_files:
                print(_process_single_view(view_file))
        else:
            with ThreadPoolExecutor(max_workers=number_of_workers) as executor:
                futures = [executor.submit(_process_single_view, view_file) for view_file in self.view_files]
                for future in concurrent.futures.as_completed(futures):
                    try:
                        print(future.result())
                    except Exception as e:
                        print(f"X Error in parallel view processing: {e}")

        print(f"Completed processing {len(self.view_files)} view animations")

    def _create_grid_gif(self, gif_paths: list[Path], grid_size: tuple = (3, 3),
                        target_size: tuple = (200, 200), fps: float = 1.0) -> None:
        """Create a grid layout GIF combining multiple individual GIFs."""
        if not gif_paths:
            print("No GIF files provided for grid creation.")
            return

        output_path = self.image_dir / "animated_results_grid_all_levels.gif"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if output_path.exists():
            output_path.unlink()

        duration = int(1000 / fps) if fps > 0 else 1000
        cols, rows = grid_size
        cell_width, cell_height = target_size
        total_width = cols * cell_width
        total_height = rows * cell_height

        gifs_data = []
        max_frames = 0

        for gif_path in gif_paths[:cols * rows]:
            gif = Image.open(gif_path)
            frames = []
            try:
                while True:
                    frame = gif.copy().resize((cell_width, cell_height), Image.Resampling.LANCZOS)
                    frames.append(frame)
                    gif.seek(gif.tell() + 1)
            except EOFError:
                pass

            gifs_data.append(frames)
            max_frames = max(max_frames, len(frames))

        grid_frames = []
        for frame_idx in range(max_frames):
            grid_frame = Image.new('RGB', (total_width, total_height), (0, 0, 0))

            for i, gif_frames in enumerate(gifs_data):
                row = i // cols
                col = i % cols
                frame = gif_frames[frame_idx % len(gif_frames)]
                x = col * cell_width
                y = row * cell_height
                grid_frame.paste(frame, (x, y))

            grid_frames.append(grid_frame)

        if grid_frames:
            grid_frames[0].save(output_path, save_all=True, append_images=grid_frames[1:],
                              duration=duration, loop=0)
            print(f"Created grid animation: {len(grid_frames)} frames, {len(gifs_data)} views in {cols}x{rows} grid")

def _process_parallel(items: list, worker_func, num_workers: int):
    """Execute worker function on items in parallel or sequentially."""
    if num_workers == 1:
        for item in items:
            print(worker_func(item))
    else:
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            for future in concurrent.futures.as_completed([executor.submit(worker_func, item) for item in items]):
                print(future.result())

def _load_font(font_size: int) -> ImageFont.FreeTypeFont:
    """Load Arial font or fallback to default."""
    try:
        return ImageFont.truetype("arial.ttf", font_size)
    except (OSError, IOError):
        return ImageFont.load_default()

def _stamp_tiff_files_combined(tiff_paths: list[Path], latitude: float, ffl_offset: float,
                               metadata_font_size: int = 24, metadata_color: tuple = (255, 255, 0),
                               metadata_bg_alpha: int = 0, padding: int = 10,
                               aoi_lineweight: int = 1, aoi_font_size: int = 32,
                               aoi_color: tuple = (255, 0, 0), aoi_bg_alpha: int = 180,
                               number_of_workers: int = 10) -> None:
    """Stamp TIFF files with both metadata AND AOI polygons in a single pass.

    Combines _stamp_tiff_files_with_metadata and _stamp_tiff_files_with_aoi
    to eliminate redundant file I/O operations (2x faster than separate calls).
    """
    if not tiff_paths:
        return

    # Load AOI files once at the start
    aoi_dir = config.AOI_DIR
    aoi_files = list(aoi_dir.glob("*.aoi")) if aoi_dir.exists() else []

    # Parse all AOI files once (not per-image)
    parsed_aois = {}
    for aoi_file in aoi_files:
        try:
            with open(aoi_file, 'r') as f:
                lines = [line.strip() for line in f.readlines()]

            perimeter_pixels = [(int(parts[2]), int(parts[3]))
                               for line in lines[5:] if line and ' ' in line
                               if (parts := line.split()) and len(parts) >= 4]

            central_pixel = (sum(p[0] for p in perimeter_pixels) // len(perimeter_pixels),
                            sum(p[1] for p in perimeter_pixels) // len(perimeter_pixels)) if perimeter_pixels else None

            aoi_data = {
                'apartment_room': lines[0].replace("AOI Points File: ", ""),
                'view_file': lines[1].replace("ASSOCIATED VIEW FILE: ", ""),
                'z_height': float(lines[2].replace("FFL z height(m): ", "")),
                'central_pixel': central_pixel,
                'perimeter_pixels': perimeter_pixels
            }

            # Group by view file for faster lookup
            view = aoi_data['view_file']
            if view not in parsed_aois:
                parsed_aois[view] = []
            parsed_aois[view].append(aoi_data)
        except Exception as e:
            print(f"Error parsing {aoi_file}: {e}")

    def _stamp_combined(tiff_path: Path) -> str:
        try:
            if not tiff_path.exists():
                return f"Not found: {tiff_path.name}"

            filename = tiff_path.stem

            # Open image once
            image = Image.open(tiff_path).convert('RGBA')
            draw = ImageDraw.Draw(image)

            # ===== PART 1: Add Metadata Stamp =====
            current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M")
            level, timestep = "Unknown", "Unknown"

            if ts := re.search(r'(\d{4}_\d{4})', filename):
                ts_str = ts.group(1)
                timestep = f"{MONTH_NAMES[int(ts_str[:2])-1]} {int(ts_str[2:4])} {ts_str[5:7]}:{ts_str[7:9]}"

            if level_match := re.search(r'[_]?L(\d+)', filename):
                level = f"L{level_match.group(1)}"

            metadata_text = f"Created: {current_datetime}, Level: {level}, Timestep: {timestep}, Latitude: {latitude}, FFL Offset: {ffl_offset}m"
            metadata_font = _load_font(metadata_font_size)

            # Calculate metadata text position (bottom-right)
            bbox = draw.textbbox((0, 0), metadata_text, font=metadata_font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            x, y = image.width - tw - padding, image.height - th - padding

            # Draw metadata background
            if metadata_bg_alpha > 0:
                overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
                overlay_draw = ImageDraw.Draw(overlay)
                overlay_draw.rectangle([x - padding//2, y - padding//2, x + tw + padding//2, y + th + padding//2],
                                      fill=(0, 0, 0, metadata_bg_alpha))
                image = Image.alpha_composite(image, overlay)
                draw = ImageDraw.Draw(image)  # Recreate draw object after composite

            # Draw metadata text
            draw.text((x, y), metadata_text, font=metadata_font, fill=metadata_color + (255,))

            # ===== PART 2: Add AOI Polygons and Labels =====
            rooms = 0
            if aoi_files and (match := re.search(r'plan_L\d+', filename)):
                view_file = f"{match.group(0)}.vp"
                matching_aois = parsed_aois.get(view_file, [])

                if matching_aois:
                    aoi_font = _load_font(aoi_font_size)

                    for aoi in matching_aois:
                        if len(aoi['perimeter_pixels']) < 3:
                            continue

                        # Draw polygon perimeter
                        polygon = aoi['perimeter_pixels'] + [aoi['perimeter_pixels'][0]]
                        for i in range(len(polygon) - 1):
                            draw.line([polygon[i], polygon[i + 1]], fill=aoi_color, width=aoi_lineweight)

                        # Draw room label at center
                        if cp := aoi['central_pixel']:
                            label = aoi['apartment_room']
                            bbox = draw.textbbox((0, 0), label, font=aoi_font)
                            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                            lx, ly = cp[0] - tw // 2, cp[1] - th // 2

                            if aoi_bg_alpha > 0:
                                draw.rectangle([lx - 5, ly - 5, lx + tw + 5, ly + th + 5],
                                              fill=(0, 0, 0, aoi_bg_alpha))
                            draw.text((lx, ly), label, font=aoi_font, fill=aoi_color + (255,))
                            rooms += 1

            # Save once with all stamps applied
            image.save(tiff_path, format='TIFF')
            return f"Stamped {tiff_path.name}: metadata + {rooms} rooms"
        except Exception as e:
            return f"Error {tiff_path.name}: {e}"

    print(f"Combined stamping: {len(tiff_paths)} files with metadata + AOI using {number_of_workers} workers")
    _process_parallel(tiff_paths, _stamp_combined, number_of_workers)
    print(f"Completed combined stamping")


