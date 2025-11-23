"""Results Processor for Working Plan Data (WPD) Generation.

This module handles the extraction and processing of illuminance data from HDR images,
filtering points within Areas of Interest (AOI), and generating compliance reports.
"""

# Archilume imports
from archilume import utils

# Standard library imports
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import pandas as pd
import logging

# Third-party imports


logger = logging.getLogger(__name__)


def ray_casting_batch(points, polygon):
    """
    Check multiple points at once.

    Args:
        points: List of points [(x1,y1), (x2,y2), ...]
        polygon: Polygon vertices

    Returns:
        List[bool]: Inside/outside status for each point
    """

    def _ray_casting_robust(point, polygon, include_boundary=True):
        """
        Robust ray casting with boundary handling.

        Args:
            point: Test point (x, y)
            polygon: List of vertices [(x1,y1), (x2,y2), ...]
            include_boundary: If True, points on edges are considered inside

        Returns:
            bool: True if inside (or on boundary if include_boundary=True)
        """
        x, y = point
        n = len(polygon)
        inside = False
        epsilon = 1e-10  # Small value for floating point comparison

        j = n - 1
        for i in range(n):
            xi, yi = polygon[i]
            xj, yj = polygon[j]

            # Check if point is exactly on vertex
            if abs(x - xi) < epsilon and abs(y - yi) < epsilon:
                return include_boundary

            # Check if point is on edge
            if min(yi, yj) <= y <= max(yi, yj):
                if min(xi, xj) <= x <= max(xi, xj):
                    # Check if point is colinear with edge
                    if abs((y - yi) * (xj - xi) - (x - xi) * (yj - yi)) < epsilon:
                        return include_boundary

            # Standard ray casting check
            if ((yi > y) != (yj > y)) and \
            (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside

            j = i

        return inside

    results = []
    for point in points:
        results.append(_ray_casting_robust(point, polygon))

    return results

@dataclass
class WPDPoint:
    """Represents a single point with illuminance data from pvalue output."""
    x: float
    y: float
    z: float
    red: float
    green: float
    blue: float
    illuminance: Optional[float] = None

    def is_non_zero(self) -> bool:
        """Check if point has non-zero illuminance values."""
        return any([self.red > 0, self.green > 0, self.blue > 0])


@dataclass
class AOIPolygon:
    """Represents an Area of Interest polygon boundary."""
    name: str
    vertices: List[Tuple[float, float]]  # List of (x, y) coordinates

    def contains_point(self, point: Tuple[float, float]) -> bool:
        """Check if a point falls within this polygon boundary."""
        result = ray_casting_batch([point], self.vertices)
        return result[0]


@dataclass
class TimeStepResult:
    """Results for a single time step analysis."""
    timestamp: str  # e.g., "0621_1500" for June 21, 3:00 PM
    hdr_image_path: Path
    total_points: int = 0
    non_zero_points: int = 0
    points_per_aoi: Dict[str, List[WPDPoint]] = field(default_factory=dict)

    def add_points_to_aoi(self, aoi_name: str, points: List[WPDPoint]) -> None:
        """Add filtered points to a specific AOI."""
        self.points_per_aoi[aoi_name] = points


@dataclass
class ResultsProcessor:
    """Main processor for generating Working Plan Data from HDR images.

    This class handles:
    - Extracting point data from HDR images using pvalue
    - Filtering non-zero illuminance points
    - Matching points to AOI polygons using ray casting
    - Writing individual .wpd files per timestep
    - Aggregating results into a single CSV for analysis
    """

    # Input parameters (required fields first)
    aoi_dir: Path
    wpd_dir: Path

    # Optional input parameters (fields with defaults)
    rendering_commands: List[str] = None  # List of direct sun rendering commands to execute
    use_modified_aoi: bool = True  # Prefer modified AOI files if they exist
    num_workers: Optional[int] = None  # None = use all available cores

    # Populated during processing
    pvalue_commands: List[str] = field(default_factory=list)
    aoi_polygons: List[AOIPolygon] = field(default_factory=list)
    timestep_results: List[TimeStepResult] = field(default_factory=list)

    def __post_init__(self):
        """Initialize output directories."""
        self.wpd_dir.mkdir(parents=True, exist_ok=True)

    def load_aoi_files(self) -> None:
        """Load AOI polygon definitions from files.

        Checks for modified AOI files first if use_modified_aoi is True,
        falls back to source AOI files otherwise.
        """
        # TODO: Implement AOI file loading logic
        pass

    def extract_points_from_hdr(self, hdr_path: Path) -> List[WPDPoint]:
        """Extract illuminance point data from HDR image using pvalue.

        Runs: pvalue -b +di <hdr_path> > temp_points.txt
        Parses output into WPDPoint objects.

        Args:
            hdr_path: Path to HDR image file

        Returns:
            List of WPDPoint objects with illuminance data
        """
        # TODO: Implement pvalue extraction
        pass

    def filter_non_zero_points(self, points: List[WPDPoint]) -> List[WPDPoint]:
        """Filter points to retain only those with non-zero illuminance values.

        Args:
            points: List of all WPDPoint objects

        Returns:
            Filtered list containing only non-zero points
        """
        return [p for p in points if p.is_non_zero()]

    def assign_points_to_aoi(self, points: List[WPDPoint]) -> Dict[str, List[WPDPoint]]:
        """Assign points to their respective AOI polygons using ray casting.

        Uses geometry_utils.ray_casting_batch for efficient batch processing.

        Args:
            points: List of WPDPoint objects to classify

        Returns:
            Dictionary mapping AOI names to lists of contained points
        """
        # TODO: Implement batch ray casting for all AOI polygons
        pass

    def process_single_timestep(self, hdr_path: Path, timestamp: str) -> TimeStepResult:
        """Process a single HDR image timestep.

        Complete workflow:
        1. Extract points using pvalue
        2. Filter non-zero points
        3. Assign points to AOI polygons
        4. Return structured results

        Args:
            hdr_path: Path to HDR image
            timestamp: Timestamp identifier (e.g., "0621_1500")

        Returns:
            TimeStepResult containing all processed data
        """
        # TODO: Implement single timestep processing
        pass

    def process_all_timesteps(self) -> None:
        """Process all HDR images using multiprocessing.

        Discovers all HDR files in image_dir and processes them in parallel.
        """
        # TODO: Implement multiprocess batch processing
        pass

    def write_wpd_file(self, result: TimeStepResult) -> Path:
        """Write a single .wpd file for a timestep.

        Format includes header with metadata and point data rows.

        Args:
            result: TimeStepResult to write

        Returns:
            Path to written .wpd file
        """
        # TODO: Implement WPD file writing
        pass

    def aggregate_to_csv(self) -> pd.DataFrame:
        """Aggregate all timestep results into a single CSV.

        Format:
        - Rows: Spatial zones (AOI names)
        - Columns: Timesteps
        - Values: Illuminance metrics (average, max, point count, etc.)

        Returns:
            DataFrame with aggregated results
        """
        # TODO: Implement CSV aggregation
        pass

    def sunlight_sequence_wpd_extraction(self) -> None:
        """Execute the complete WPD generation pipeline.

        Phases:
        0. Process and filter .hdr for non-zero pixels.
        1. Load .aoi files (prefer modified if available)
        2. Process sunlit points within .aoi (multiprocess)
        3. Write individual .wpd files
        4. Generate aggregated .csv

        Returns:
            Path to final .csv results file
        """
        self.pvalue_commands = self._generate_hdr_points_extraction_commands()
        utils.execute_new_pvalue_commands(self.pvalue_commands, number_of_workers=14, threshold=1e-9)

        # self.load_aoi_files()
        # self.process_all_timesteps()

        # # Write individual WPD files
        # for result in self.timestep_results:
        #     self.write_wpd_file(result)

        # # Generate CSV
        # df = self.aggregate_to_csv()
        # df.to_csv(self.output_csv_path)

        print("Sunlight sequenece wpd extraction completed successfully.")

    def _generate_hdr_points_extraction_commands(self) -> list[str]:
        """
        Generate Radiance commands for extracting point illuminance data from HDR images.
        """

        pvalue_commands = []

        for rendering_command in self.rendering_commands:

            # Extract the HDR file path (everything after the last ">")
            hdr_file_path = Path(rendering_command.split('>')[-1].strip())

            # Generate output path for point data (replace .hdr with .txt in wpd directory)
            output_txt_path = self.wpd_dir / hdr_file_path.name.replace('.hdr', '.txt')

            # Construct pvalue command: pvalue -b +di <input.hdr> > <output.txt>
            pvalue_command = f'pvalue -b +di {hdr_file_path} > {output_txt_path}'

            pvalue_commands.append(pvalue_command)

        # Log summary before exit
        logger.info(
            f"Generated points extraction commands: {len(pvalue_commands)} pvalue commands"
        )

        return pvalue_commands



