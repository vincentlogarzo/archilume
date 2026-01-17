# Archilume imports
from archilume import (
    MtlConverter,
    config
    )

# Standard library imports
import os
import sys
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# Third-party imports
import pyradiance

@dataclass
class Objs2Octree:
    """
    Converts material definitions from Wavefront .mtl files
    (e.g., exported from Revit) into Radiance material description files.
    Supports multiple OBJ/MTL file pairs for complex scenes with site and building geometry.

    The converter processes common .mtl properties like diffuse color ('Kd')
    and dissolve/opacity ('d') to create Radiance 'plastic' (for opaque)
    or 'glass' (for transparent/translucent) materials.

    Attributes:
        input_obj_paths (list[Path]): List of OBJ file paths to process
        input_mtl_paths (list[Path]): List of corresponding MTL file paths
    """

    # User inputs - support multiple files
    input_obj_paths: list[Path]             = None

    # Internal output file paths (set automatically during processing)
    input_mtl_paths: list[Path]             = field(init=False, default=None)
    combined_radiance_mtl_path: str | None  = field(init=False, default=None)
    output_rad_paths: list[str]             = field(init=False, default=None)
    output_dir: Path                        = field(init=False, default_factory=lambda: config.OCTREE_DIR)
    skyless_octree_path: Path               = field(init=False, default=None)
    
    def __post_init__(self):
        """Initialize lists if None and validate input."""
        if self.input_obj_paths is None:
            print("Warning: no input files, terminating now")
            exit()
         # Handle single Path or list of Paths
        if isinstance(self.input_obj_paths, Path): 
            self.input_obj_paths = [self.input_obj_paths]
        if self.input_mtl_paths is None: 
            self.input_mtl_paths = []
        if self.output_rad_paths is None: 
            self.output_rad_paths = []
        
        if not os.path.exists(self.output_dir):
            try:
                os.makedirs(self.output_dir)
                print(f"Created output directory: {self.output_dir}")
            except OSError as e:
                print(f"Error creating directory {self.output_dir}: {e}")
        
        # Create mtl paths from input obj paths
        self.input_mtl_paths = [Path(input_obj_path).with_suffix('.mtl') for input_obj_path in self.input_obj_paths]

    def create_skyless_octree_for_analysis(self) -> None:
        """
        Process all OBJ/MTL file pairs: convert OBJ to RAD, parse MTL to Radiance format,
        and add missing modifiers. This is the main method to call for multi-file processing.
        """
        if not self.input_obj_paths or not self.input_mtl_paths:
            print("No files to process")
            return
            
        print(f"Processing OBJ/MTL file pairs...")
        
        # Check if octree already exists before doing any processing
        obj_name = self.input_obj_paths[0].stem
        self.skyless_octree_path = self.output_dir / f"{obj_name}_with_site_skyless.oct"
        
        if self.skyless_octree_path.exists():
            print(f"Skyless octree already exists: {self.skyless_octree_path}")
            return
        
        # --- Step 1: Convert all OBJ files to RAD ---
        try:
            self.__obj2rad_with_os_system()

        except Exception as e:
            print(f"Error running obj2rad: {e}")
        
        # --- Step 2: Create radiance materials description from all mtl files and cross reference modifiers contained in rad files created ---
        if self.output_rad_paths:
            mtl_creator = MtlConverter(
                rad_paths=self.output_rad_paths,
                mtl_paths=self.input_mtl_paths
            )
            mtl_creator.create_radiance_mtl_file()

            print("Material file created at:", mtl_creator.output_mtl_path)

            self.combined_radiance_mtl_path = mtl_creator.output_mtl_path

        # --- Step 3: Combine all rad files and combined radiance material file from step 1 and 2 into an octree ---
        self.__rad2octree()

    def __obj2rad_with_os_system(self, exe_path: Path = None) -> int:
        """
        Convert OBJ files to RAD format using obj2rad from pyradiance or system Radiance.
        """
        # Auto-detect obj2rad executable (platform-aware)
        if exe_path is None:
            if sys.platform == "win32":
                exe_path = config.RADIANCE_BIN_PATH / "obj2rad.exe"
            else:
                exe_path = config.RADIANCE_BIN_PATH / "obj2rad"

        for input_obj_path in self.input_obj_paths:

            output_rad_path = config.RAD_DIR / input_obj_path.with_suffix('.rad').name
            self.output_rad_paths.append(output_rad_path)

            # Build the command string with proper quoting for paths with spaces
            command = f'"{exe_path}" "{input_obj_path}" > "{output_rad_path}"'
            print(f"Running: {command}")

            exit_code = os.system(command)

            # On Unix, os.system returns exit status << 8, so divide by 256
            if sys.platform != "win32":
                exit_code = exit_code >> 8

            if exit_code == 0:
                print("Command executed successfully")
            else:
                print(f"Command failed with exit code: {exit_code}")
                return exit_code  # Return immediately on failure

        return 0  # Return 0 if all commands succeeded
   
    def __rad2octree(self) -> None:
        """
        Runs the oconv command to generate frozen skyless octree for rendering from all RAD files.
        Output is placed in the same directory as the RAD/MTL files with fixed name '{original_obj_name}.oct'.
        Must use command prompt instead of powershell in VScode as its default encoding is utf-16 if  run in the shell,
        instead of the required encoding of utf-8 required for oconv.
        Example command: oconv -f material_file.mtl file1.rad file2.rad > output.oct
        """
        if not self.output_rad_paths or not self.combined_radiance_mtl_path:
            print("No RAD files or material file available for octree generation")
            return
        
        # Build command with material file and all RAD files using pathlib
        rad_files_str = " ".join(f'"{Path(rad_path)}"' for rad_path in self.output_rad_paths)
        command = f'oconv -f "{Path(self.combined_radiance_mtl_path)}" {rad_files_str} > "{self.skyless_octree_path}"'
        
        print(f"Generating octree from {len(self.output_rad_paths)} RAD files...")
        print(f"Command: {command}")
        
        try:
            # Use subprocess.run with shell=True for Windows compatibility
            result = subprocess.run(
                command, 
                shell=True,
                capture_output=True, 
                text=True,
                encoding='utf-8'
            )
            
            if result.returncode == 0:
                print(f"Successfully generated: {self.skyless_octree_path}")
                if self.skyless_octree_path.exists():
                    print(f"Octree file size: {self.skyless_octree_path.stat().st_size} bytes")
            else:
                print(f"Warning: oconv returned code {result.returncode}")
                print(f"STDERR: {result.stderr}")
                if self.skyless_octree_path.exists():
                    print(f"Octree file created despite warnings: {self.skyless_octree_path}")
                    print(f"Octree file size: {self.skyless_octree_path.stat().st_size} bytes")
                    
        except Exception as e:
            print(f"Error generating octree: {e}")


