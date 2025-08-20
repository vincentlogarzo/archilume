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
            self.combined_rad_paths = []
        
        # Set output directory as absolute path
        self.output_dir = Path.cwd() / "intermediates" / "rad"
        
        # Validate that we have equal number of OBJ and MTL files
        if len(self.obj_paths) != len(self.mtl_paths):
            raise ValueError("Number of OBJ files must match number of MTL files")

    def obj2rad(self, input_obj: Path) -> None:
        
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

        #subprocess.run('obj2rad "c:\\Projects\\archilume\\inputs\\87cowles_BLD_noWindows.obj" > "c:\\Projects\\archilume\\intermediates\\octrees\\87cowles_BLD_noWindows.rad"', shell=True)
        
        try:
            # Ensure output directory exists
            output_rad.parent.mkdir(parents=True, exist_ok=True)
            
            # 'obj2rad "c:\\Projects\\archilume\\inputs\\87cowles_BLD_noWindows.obj" > "c:\\Projects\\archilume\\intermediates\\octrees\\87cowles_BLD_noWindows.rad"'

            # Run the obj2rad command with full path
            obj2rad_exe = r"C:\Program Files\Radiance\bin\obj2rad.exe" #TODO: this is problematic as it required the user to have radiance installed and in this location. 
            with open(output_rad, "w") as rad_output:
                subprocess.run([obj2rad_exe, str(input_obj)], stdout=rad_output, check=True)
            
            # Verify if the rad_file was created
            if not os.path.exists(output_rad):
                raise FileNotFoundError(f"Expected RAD file not found: {output_rad}")
                
            print(f"Successfully converted: {os.path.basename(output_rad)}")
        
        except Exception as e:
            print(f"Error converting {input_obj}: {e}")
    

    def _convert_rads_to_octree(self) -> None:
        """
        Runs the oconv command to generate frozen skyless octree for rendering from all RAD files.
        Output is placed in the same directory as the RAD/MTL files with fixed name '!combined_scene_skyless.oct'.
        Must use command prompt instead of powershell in VScode as its default encoding is utf-8
        instead of the required encoding for oconv.
        Example command: oconv -f material_file.mtl file1.rad file2.rad > output.oct
        """
        if not self.rad_paths or not self.combined_radiance_mtl_path:
            print("No RAD files or material file available for octree generation")
            return
        
        # Use pathlib for cross-platform path handling
        output_dir = Path(self.output_dir)
        output_filename = output_dir / "!combined_scene_skyless.oct"
        
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

    def _create_basic_material_file(self) -> None:
        """Create a basic Radiance material file with common materials."""
        if os.path.exists(self.combined_radiance_mtl_path):
            return
            
        basic_materials = """
# Basic default material
void plastic default_material
0
0
5 0.7 0.7 0.7 0.0 0.05

# Glass material  
void glass default_glass
0
0
3 0.96 0.96 0.96

# Concrete material
void plastic concrete
0  
0
5 0.8 0.8 0.8 0.0 0.1
"""
        
        with open(self.combined_radiance_mtl_path, 'w', encoding='utf-8') as f:
            f.write(basic_materials)
        print(f"Created basic material file: {self.combined_radiance_mtl_path}")

    def create_skyless_octree_for_analysis(self) -> None:
        """
        Process all OBJ/MTL file pairs: convert OBJ to RAD, parse MTL to Radiance format,
        and add missing modifiers. This is the main method to call for multi-file processing.
        """
        if not self.obj_paths or not self.mtl_paths:
            print("No files to process")
            return
            
        print(f"Processing {len(self.obj_paths)} OBJ/MTL file pairs...")
        
        # Convert all OBJ files to RAD
        self.rad_paths = []
        for obj_path in self.obj_paths:
            try:
                self.obj2rad(obj_path)
            except Exception as e:
                print(f"Error converting {obj_path}: {e}")
                continue

        #TODO: complete the below class to create readiance material description file. 
        
        # Parse and combine all MTL files
        if self.rad_paths:
            mtl_creator = CreateRadianceMtlFile(
                rad_paths=self.rad_paths,
                mtl_paths=self.mtl_paths
            )
            # Set the path to the combined material file for octree generation
            self.combined_radiance_mtl_path = os.path.join(self.output_dir, "combined_radiance.mtl")
            # Create a basic material file if it doesn't exist
            self._create_basic_material_file()
            self.combined_rad_paths = self.rad_paths
        else:
            print("No RAD files created - skipping material file creation")

        # Combine all rad file and mtl files converted to radiance description files into one octree
        self._convert_rads_to_octree()
