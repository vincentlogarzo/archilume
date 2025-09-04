# Archilume imports
from .create_radiance_mtl_file import CreateRadianceMtlFile
from .utils import run_commands_parallel

# Standard library imports
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# Third-party imports



@dataclass
class ObjToOctree:
    """
    Converts material definitions from Wavefront .mtl files
    (e.g., exported from Revit) into Radiance material description files.
    Supports multiple OBJ/MTL file pairs for complex scenes with site and building geometry.

    The converter processes common .mtl properties like diffuse color ('Kd')
    and dissolve/opacity ('d') to create Radiance 'plastic' (for opaque)
    or 'glass' (for transparent/translucent) materials.

    Attributes:
        obj_paths (list[str]): List of OBJ file paths to process
        mtl_paths (list[str]): List of corresponding MTL file paths
    """

    # User inputs - support multiple files
    obj_paths: list[str] = None
    mtl_paths: list[str] = None
    
    # Internal output file paths (set automatically during processing)
    combined_radiance_mtl_path: str | None = field(init=False, default=None)
    rad_paths: list[str] = field(init=False, default=None)
    output_dir: str = field(init=False, default=None)
    
    def __post_init__(self):
        """Initialize lists if None and validate input."""
        if self.obj_paths is None:
            self.obj_paths = []
        if self.mtl_paths is None:
            self.mtl_paths = []
        if self.rad_paths is None:
            self.rad_paths = []
        
        # Set output directory as absolute path
        self.output_dir = Path.cwd() / "intermediates" / "rad"
        
        # Validate that we have equal number of OBJ and MTL files
        if len(self.obj_paths) != len(self.mtl_paths):
            raise ValueError("Number of OBJ files must match number of MTL files")

    def _obj2rad(self, input_obj_path: Path, exe_directory: str = None) -> None:
        """
        Converts a Wavefront OBJ file to Radiance RAD format using the obj2rad utility.
        
        This method calls the external Radiance obj2rad executable to convert a 3D geometry
        file from OBJ format (commonly exported from CAD software like Revit) into the 
        RAD format required for Radiance lighting simulations.
        
        Args:
            input_obj (Path): Path to the input .obj file to be converted
            
        Raises:
            ValueError: If input_obj is not a Path object
            FileNotFoundError: If the expected output RAD file is not created
            subprocess.CalledProcessError: If the obj2rad command fails
            
        Note:
            - Requires Radiance to be installed at C:\\Program Files\\Radiance\\bin\\obj2rad.exe
            - Output RAD files are saved to {project_root}/intermediates/rad/ directory
            - The output directory is created automatically if it doesn't exist
            - This is a conversion step in the larger workflow of creating octree files for analysis
            
        Example:
            >>> converter = ObjToOctree(["model.obj"], ["model.mtl"])
            >>> converter.obj2rad(Path("model.obj"))
            Successfully converted: model.rad
            >>> # Example 1:  # subprocess.run('obj2rad "c:\\Projects\\archilume\\inputs\\87cowles_BLD_noWindows.obj" > "c:\\Projects\\archilume\\intermediates\\rad\\87cowles_BLD_noWindows.rad"', shell=True)
        """

        output_file_path = Path(__file__).parent.parent / "intermediates" / "rad" / input_obj_path.with_suffix('.rad').name

        command = f'obj2rad {input_obj_path} > {output_file_path}'

        # subprocess.run(command, shell=True, encoding='utf-8')
        
        run_commands_parallel([command], max_workers=1)

        if not output_file_path.exists():
            raise FileNotFoundError(f"Expected RAD file not found: {output_file_path}")
        else:
            print(f"Successfully converted: {output_file_path}")
   
    def _rads2octree(self) -> None:
        """
        Runs the oconv command to generate frozen skyless octree for rendering from all RAD files.
        Output is placed in the same directory as the RAD/MTL files with fixed name '{original_obj_name}.oct'.
        Must use command prompt instead of powershell in VScode as its default encoding is utf-8
        instead of the required encoding for oconv.
        Example command: oconv -f material_file.mtl file1.rad file2.rad > output.oct
        Example command: oconv -f "C:\Projects\archilume\intermediates\rad\materials.mtl" "C:\Projects\archilume\intermediates\rad\87cowles_site.rad" "C:\Projects\archilume\intermediates\rad\87cowles_BLD_noWindows.rad" > "C:\Projects\archilume\intermediates\octree\87cowles_BLD_noWindows_with_site.oct"
        """
        if not self.rad_paths or not self.combined_radiance_mtl_path:
            print("No RAD files or material file available for octree generation")
            return
        
        # Use pathlib for cross-platform path handling
        output_dir = Path(self.output_dir)
        obj_name = Path(self.obj_paths[0]).stem
        output_filename = output_dir / f"{obj_name}.oct"
        
        # Build command with material file and all RAD files using pathlib
        rad_files_str = " ".join(f'"{Path(rad_path)}"' for rad_path in self.rad_paths)
        command = f'oconv -f "{Path(self.combined_radiance_mtl_path)}" {rad_files_str} > "{output_filename}"'
        
        print(f"Generating octree from {len(self.rad_paths)} RAD files...")
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
                print(f"Successfully generated: {output_filename}")
                if output_filename.exists():
                    print(f"Octree file size: {output_filename.stat().st_size} bytes")
            else:
                print(f"Warning: oconv returned code {result.returncode}")
                print(f"STDERR: {result.stderr}")
                if output_filename.exists():
                    print(f"Octree file created despite warnings: {output_filename}")
                    print(f"Octree file size: {output_filename.stat().st_size} bytes")
                    
        except Exception as e:
            print(f"Error generating octree: {e}")

    def create_skyless_octree_for_analysis(self) -> None:
        """
        Process all OBJ/MTL file pairs: convert OBJ to RAD, parse MTL to Radiance format,
        and add missing modifiers. This is the main method to call for multi-file processing.
        """
        if not self.obj_paths or not self.mtl_paths:
            print("No files to process")
            return
            
        print(f"Processing OBJ/MTL file pairs...")
        
        # --- Step 1: Convert all OBJ files to RAD ---
        self.rad_paths = []
        for obj_path in self.obj_paths:
            try:
                # Call obj2rad (creates RAD file in same directory as OBJ)
                self._obj2rad(Path(obj_path))
                
                # obj2rad creates the RAD file next to the OBJ file
                source_rad = Path(obj_path).resolve().with_suffix('.rad')
                
                # Copy to our target directory
                output_dir = Path(self.output_dir)
                output_dir.mkdir(parents=True, exist_ok=True)
                target_rad = output_dir / source_rad.name
                
                if source_rad.exists():
                    # Copy the file to target directory
                    import shutil
                    shutil.copy2(source_rad, target_rad)
                    self.rad_paths.append(str(target_rad))
                    print(f"Successfully converted and copied {obj_path} to {target_rad}")
                else:
                    print(f"Error: RAD file not created at {source_rad}")
                    
            except Exception as e:
                print(f"Error converting {obj_path}: {e}")
                continue
        
        # --- Step 2: Create combine radiance materials description from all mtl files ---
        if self.rad_paths:
            mtl_creator = CreateRadianceMtlFile(
                rad_paths=self.rad_paths,
                mtl_paths=self.mtl_paths
            )
            mtl_creator.create_radiance_mtl_file()

            print("Material file created at:", mtl_creator.output_mtl_path)
        
        
        # --- Step 3: Combine all rad files and combined radiance material file from step 1 and 2 into an octree ---
        self._rads2octree()
