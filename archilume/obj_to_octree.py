# Archilume imports
from archilume.create_radiance_mtl_file import CreateRadianceMtlFile

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

    def _obj2rad(self, input_obj: Path) -> None:
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
            >>> # Example 1:  'obj2rad "c:\\Projects\\archilume\\inputs\\87cowles_BLD_noWindows.obj" > "c:\\Projects\\archilume\\intermediates\\octrees\\87cowles_BLD_noWindows.rad"'
            >>> # Example 2:  # Subprocess.run('obj2rad "c:\\Projects\\archilume\\inputs\\87cowles_BLD_noWindows.obj" > "c:\\Projects\\archilume\\intermediates\\octrees\\87cowles_BLD_noWindows.rad"', shell=True)
        """
        
        def _create_output_path(input_obj: Path) -> Path:
            """
            Create an output path for the .rad file based on the input .obj file.
            """
            # 1. Ensure the input is a Path object
            if not isinstance(input_obj, Path):
                raise ValueError("Input must be a Path object")
            
            project_root = input_obj.parent.parent
            output_dir = project_root / "intermediates" / "rad"
            output_rad = output_dir / input_obj.with_suffix('.rad').name

            return output_rad
        
        output_rad = _create_output_path(input_obj)

        try:
            # Ensure output directory exists
            output_rad.parent.mkdir(parents=True, exist_ok=True)

            # Run the obj2rad command - try multiple possible locations
            # TODO: future should determine how to use the obj2rad from the venv otherwise a user has to install radiance on their computer and add it to thier path environment variables. 
            possible_paths = [
                Path("C:/Program Files/Radiance/bin/obj2rad.exe"),
                Path("obj2rad.exe")  # Fallback to PATH
            ]
            
            obj2rad_exe = None
            for path in possible_paths:
                if path.exists() or path.name == "obj2rad.exe":  # Last one relies on PATH
                    obj2rad_exe = path
                    break
            
            if obj2rad_exe is None:
                raise FileNotFoundError("obj2rad.exe not found in expected locations")
            with open(output_rad, "w") as rad_output:
                subprocess.run([obj2rad_exe, str(input_obj)], stdout=rad_output, check=True)
            
            # Verify if the rad_file was created
            if not os.path.exists(output_rad):
                raise FileNotFoundError(f"Expected RAD file not found: {output_rad}")
                
            print(f"Successfully converted: {os.path.basename(output_rad)}")
        
        except Exception as e:
            print(f"Error converting {input_obj}: {e}")
    
    def _rads2octree(self) -> None:
        """
        Runs the oconv command to generate frozen skyless octree for rendering from all RAD files.
        Output is placed in the same directory as the RAD/MTL files with fixed name '{original_obj_name}.oct'.
        Must use command prompt instead of powershell in VScode as its default encoding is utf-8
        instead of the required encoding for oconv.
        Example command: oconv -f material_file.mtl file1.rad file2.rad > output.oct
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
                self._obj2rad(Path(obj_path))
                # Add the output rad file path to our list
                output_dir = Path(self.output_dir)
                rad_file = output_dir / Path(obj_path).with_suffix('.rad').name
                if rad_file.exists():
                    self.rad_paths.append(str(rad_file))
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
