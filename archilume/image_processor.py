"""
This code uses three main radiance programmes: 
oconv - compile an octree which is a file ready to be rendered
rpict - rendering a scene using a view and the above octree
ra_tiff - convert output hdr file format to tiff or simple viewing. 
"""

# Archilume imports
from archilume import utils

# Standard library imports
from dataclasses import dataclass, field
from typing import List
from datetime import datetime
from pathlib import Path

# Third-party imports
from itertools import product

@dataclass
class ImageProcessor:
    """
    Post-processes rendered TIFF images with metadata annotations, AOI overlays, and animations.

    Takes pre-rendered sunlight analysis images and produces compliance documentation including:
    timestamped images, spatial boundary overlays, and temporal visualizations (GIF/MP4).

    Attributes:
        skyless_octree_path (Path): Base octree file without sky
        overcast_sky_file_path (Path): Overcast sky reference file
        sky_files_dir (Path): Directory containing .sky files
        view_files_dir (Path): Directory containing .vp view files
        image_dir (Path): Output directory for processed images
        x_res (int): Horizontal resolution in pixels
        y_res (int): Vertical resolution in pixels
        latitude (float): Project latitude in decimal degrees (e.g., -33.8248567 for Melbourne)

    Example:
        >>> processor = ImageProcessor(
        ...     skyless_octree_path=Path("scene.oct"),
        ...     sky_files_dir=Path("outputs/sky_files"),
        ...     view_files_dir=Path("outputs/view_files"),
        ...     image_dir=Path("outputs/images"),
        ...     x_res=2048, y_res=2048,
        ...     latitude=-33.8248567
        ... )
        >>> processor.sepp65_results_pipeline()
    """

    # Required fields - no defaults
    skyless_octree_path: Path
    overcast_sky_file_path: Path
    sky_files_dir: Path
    view_files_dir: Path
    image_dir: Path
    x_res: int
    y_res: int
    latitude: float
    
    # Fields that will be populated after initialization
    sky_files: List[Path]                   = field(default_factory=list, init=False)
    view_files: List[Path]                  = field(default_factory=list, init=False)

    def __post_init__(self):
        """
        Auto-populates sky_files and view_files lists from directories, validates resolution.
        """
        # Populate sky files from directory
        self.sky_files = sorted([path for path in self.sky_files_dir.glob('*.sky')])
        
        # Populate view files from directory
        self.view_files = sorted([path for path in self.view_files_dir.glob('*.vp')])
        
        # Validate resolution values
        if self.x_res <= 0 or self.y_res <= 0:
            raise ValueError(f"Resolution must be positive: x_res={self.x_res}, y_res={self.y_res}")

    def sepp65_results_pipeline(self):
        """
        Process rendered images into SEPP65 compliance documentation with annotations and animations.

        Pipeline stages:
        1. Stamp images with timestamp and location metadata
        2. Overlay AOI (Area of Interest) boundaries with labels
        3. Generate animated GIFs and MP4s for each view
        4. Create grid visualizations combining all views

        Prerequisites:
            - TIFF files matching '*_combined.tiff' must exist in image_dir
            - AOI files must be available for spatial boundary overlay

        Returns:
            None. Outputs processed files to image_dir.
        """

        # Phase 1: Apply Temporal and Contextual Annotations
        # Embed chronological and meteorological metadata for regulatory compliance verification
        tiff_files_to_stamp = [path for path in self.image_dir.glob('*_combined.tiff')]

        utils.datetime_loc_stamp_tiff(
            tiff_files_to_stamp,
            latitude=self.latitude,
            font_size=24,
            text_color=(255, 255, 255),  # Professional white annotation
            background_alpha=180,
            number_of_workers=10
        )

        # Phase 2: Architectural Space Identification and Compliance Delineation
        # Overlay spatial boundaries with occupancy classifications for regulatory assessment
        utils.stamp_tiff_files_with_aoi(
            tiff_files_to_stamp, 
            lineweight              = 1, 
            font_size               = 32, 
            text_color              = (255, 0, 0), 
            background_alpha        = 180, 
            number_of_workers       = 10
            )

        # Optimization Opportunity: Implement hierarchical stamping methodology efficiency



        # Phase 4d: Generate Comprehensive Illumination Analytics Dashboard
        # Produce calibrated visualization showing temporal illumination patterns with ADG compliance thresholds 


        # Phase 5: Synthesize Multi-Format Temporal Visualizations
        # Create animated sequences demonstrating illumination evolution across temporal cycles
        utils.combine_tiffs_by_view(self.image_dir, self.view_files, output_format='gif', number_of_workers=8)
        utils.combine_tiffs_by_view(self.image_dir, self.view_files, output_format='mp4', number_of_workers=8)


        # Phase 6: Generate Consolidated Multi-Perspective Analytics
        # Produce unified grid visualization integrating all viewpoint analyses for comprehensive assessment
        individual_view_mp4s = [path for path in self.image_dir.glob('animated_results_*.mp4')]
        utils.create_grid_mp4(individual_view_mp4s, self.image_dir, grid_size=(3, 2), target_size=(2048, 2048), fps=2)

        individual_view_gifs = [path for path in self.image_dir.glob('animated_results_*.gif')]
        utils.create_grid_gif(individual_view_gifs, self.image_dir, grid_size=(3, 2), target_size=(2048, 2048), fps=2)

        print("\nRendering sequence completed successfully.\n")
