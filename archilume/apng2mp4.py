# Archilume imports
from archilume import config

# Standard library imports
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List

# Third-party imports
import cv2
from PIL import Image
import numpy as np


@dataclass
class Apng2Mp4:
    """Convert APNG animated images to MP4 video format using OpenCV."""

    input_dir: Path = field(default_factory=lambda: config.IMAGE_DIR)
    output_dir: Optional[Path] = None
    pattern: str = "*.apng"
    fps: int = 2

    def __post_init__(self):
        """Validate inputs and set defaults."""
        self.input_dir = Path(self.input_dir)

        if not self.input_dir.exists():
            raise FileNotFoundError(f"Input directory not found: {self.input_dir}")

        if self.output_dir is None:
            self.output_dir = self.input_dir
        else:
            self.output_dir = Path(self.output_dir)
            self.output_dir.mkdir(parents=True, exist_ok=True)

        if self.fps <= 0:
            raise ValueError(f"FPS must be positive, got: {self.fps}")

    def convert(self) -> List[Path]:
        """
        Convert all APNG files matching pattern in input_dir to MP4.

        Returns:
            List[Path]: List of paths to created MP4 files
        """
        apng_files = list(self.input_dir.glob(self.pattern))
        if not apng_files:
            print(f"No files matching '{self.pattern}' found in {self.input_dir}")
            return []

        print(f"Converting {len(apng_files)} APNG files to MP4...")

        converted = []
        errors = []

        assert self.output_dir is not None
        for apng_file in apng_files:
            output_path = self.output_dir / apng_file.with_suffix('.mp4').name
            try:
                result = self._convert_single(apng_file, output_path)
                converted.append(result)
            except Exception as e:
                errors.append(f"{apng_file.name}: {e}")

        print(f"\n[OK] Converted {len(converted)}/{len(apng_files)} files")
        if errors:
            print("Errors:")
            for error in errors:
                print(f"  {error}")

        return converted

    def _convert_single(self, input_path: Path, output_path: Path) -> Path:
        """Convert a single APNG file to MP4 using OpenCV."""
        print(f"Converting: {input_path.name} -> {output_path.name}")

        # Read APNG frames using PIL
        img = Image.open(input_path)
        frames = []

        try:
            while True:
                # Convert to RGB then BGR for OpenCV
                frame = img.convert('RGB')
                frame_bgr = cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR)
                frames.append(frame_bgr)
                img.seek(img.tell() + 1)
        except EOFError:
            pass

        if not frames:
            raise ValueError(f"No frames found in {input_path}")

        # Get frame dimensions
        height, width = frames[0].shape[:2]

        # Create video writer with mp4v codec
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # type: ignore[attr-defined]
        writer = cv2.VideoWriter(str(output_path), fourcc, self.fps, (width, height))

        for frame in frames:
            writer.write(frame)

        writer.release()

        print(f"[OK] Created: {output_path}")
        return output_path


if __name__ == "__main__":
    converter = Apng2Mp4()
    converter.convert()
