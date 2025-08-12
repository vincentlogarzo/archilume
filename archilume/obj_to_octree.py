# Archilume imports
from archilume.add_missing_modifiers import AddMissingModifiers
from archilume.utils import run_commands_parallel

# Standard library imports
import os
import subprocess
from dataclasses import dataclass, field


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
        obj_file_paths (list[str]): List of OBJ file paths to process
        mtl_file_paths (list[str]): List of corresponding MTL file paths
    """

    # User inputs - support multiple files
    obj_file_paths: list[str] = None
    mtl_file_paths: list[str] = None
    
    # Internal output file paths (set automatically during processing)
    combined_radiance_mtl_path: str | None = field(init=False, default=None)
    combined_rad_paths: list[str] = field(init=False, default=None)
    output_dir: str = field(init=False, default=None)
    
    def __post_init__(self):
        """Initialize lists if None and validate input."""
        if self.obj_file_paths is None:
            self.obj_file_paths = []
        if self.mtl_file_paths is None:
            self.mtl_file_paths = []
        if self.combined_rad_paths is None:
            self.combined_rad_paths = []
        
        # Set output directory
        self.output_dir = "intermediates/octrees"
            
        # Validate that we have equal number of OBJ and MTL files
        if len(self.obj_file_paths) != len(self.mtl_file_paths):
            raise ValueError("Number of OBJ files must match number of MTL files")

    def _convert_to_radiance_materials(self, mtl_content: str) -> str:
        """
        Converts .mtl material entries to Radiance material format.
        Args:
            mtl_content: The content of the .mtl file as a string.
        Returns:
            The converted content as a string.
        """

        def __format_radiance_glass(material):
            name = material["name"]
            kd = material.get("Kd", [0.0, 0.0, 0.0])
            return [
                f"\n# {name}",
                f"void glass {name}",
                "0",
                "0",
                f"3 {kd[0]:.3f} {kd[1]:.3f} {kd[2]:.3f}",
            ]

        def __format_radiance_plastic(material):
            name = material["name"]
            kd = material.get("Kd", [0.0, 0.0, 0.0])
            return [
                f"\n# {name}",
                f"void plastic {name}",
                "0",
                "0",
                f"5 {kd[0]:.3f} {kd[1]:.3f} {kd[2]:.3f} 0.000 0.005",
            ]

        lines = mtl_content.splitlines()
        converted_lines = ["# Third line parameters: R G B Sp Rg"]
        current_material = {}

        for line in lines:
            line = line.strip()
            if line.startswith("newmtl"):
                if current_material:
                    if current_material.get("d", 1.0) < 1.0:
                        converted_lines.extend(__format_radiance_glass(current_material))
                    elif current_material.get("d", 1.0) == 1.0:
                        converted_lines.extend(__format_radiance_plastic(current_material))
                material_name = line.split(" ", 1)[1]
                current_material = {"name": material_name}
            elif line.startswith("Kd"):
                current_material["Kd"] = [float(x) for x in line.split()[1:]]
            elif line.startswith("d"):
                current_material["d"] = float(line.split()[1])
            elif line and not line.startswith("#"):
                pass

        if current_material:
            if current_material.get("d", 1.0) < 1.0:
                converted_lines.extend(__format_radiance_glass(current_material))
            elif current_material.get("d", 1.0) == 1.0:
                converted_lines.extend(__format_radiance_plastic(current_material))

        return "\n".join(converted_lines)
    
    def _obj_files_to_rad(self) -> None:
        """
        Convert all OBJ files to RAD format.
        Output RAD files are saved to intermediates/octrees directory.
        OBJ files must be exported from Revit in meters not mm.
        TODO: determine what the unit is of the obj file and prompt the user if it is not in meters.
        """
        self.combined_rad_paths = []
        
        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)
        
        for i, obj_file in enumerate(self.obj_file_paths):
            try:
                # Generate output filename in intermediates/octrees directory
                base_name = os.path.splitext(os.path.basename(obj_file))[0]
                output_rad_file_name = os.path.join(self.output_dir, f"{base_name}.rad")
                self.combined_rad_paths.append(output_rad_file_name)
                
                print(f"Converting OBJ {i+1}/{len(self.obj_file_paths)}: {os.path.basename(obj_file)}")
                print(f"  Output: {output_rad_file_name}")
                
                # Run the obj2rad command
                command = ["obj2rad", obj_file]
                with open(output_rad_file_name, "w") as rad_output:
                    subprocess.run(command, stdout=rad_output, check=True)
                
                # Verify if the rad_file was created
                if not os.path.exists(output_rad_file_name):
                    raise FileNotFoundError(f"Expected RAD file not found: {output_rad_file_name}")
                    
                print(f"Successfully converted: {os.path.basename(output_rad_file_name)}")
                
            except Exception as e:
                print(f"Error converting {obj_file}: {e}")
                # Remove failed conversion from the list
                if output_rad_file_name in self.combined_rad_paths:
                    self.combined_rad_paths.remove(output_rad_file_name)
                continue

    def _add_missing_modifiers_from_all_rads(self) -> None:
        """
        Add missing modifiers to the combined material file from all RAD files.
        """
        if not self.combined_radiance_mtl_path:
            print("No combined material file to update")
            return
            
        print(f"Adding missing modifiers from {len(self.combined_rad_paths)} RAD files...")
        
        for rad_path in self.combined_rad_paths:
            if os.path.exists(rad_path):
                print(f"Processing modifiers from: {os.path.basename(rad_path)}")
                AddMissingModifiers(rad_path, self.combined_radiance_mtl_path).process_files()
            else:
                print(f"Warning: RAD file not found: {rad_path}")

    def _parse_mtl_files(self) -> None:
        """
        Read all MTL files, convert their content, and combine into a single Radiance material file.
        Updates the combined_radiance_mtl_path with the merged material definitions.
        Also adds missing modifiers from RAD files if they exist.
        Output is saved to intermediates/octrees/combined_radiance.mtl.
        """
        if not self.mtl_file_paths:
            print("No MTL files to process")
            return
            
        all_converted_content = ["#Combined Radiance Material file:"]
        processed_materials = set()  # Track materials to avoid duplicates
        
        for i, mtl_path in enumerate(self.mtl_file_paths):
            try:
                print(f"Processing MTL file {i+1}/{len(self.mtl_file_paths)}: {mtl_path}")
                
                with open(mtl_path) as file:
                    mtl_content = file.read()

                # Convert MTL content to Radiance format
                converted_content = self._convert_to_radiance_materials(mtl_content)
                
                # Extract material names to avoid duplicates
                lines = converted_content.split('\n')
                current_section = []
                for line in lines:
                    if line.strip().startswith('void plastic ') or line.strip().startswith('void glass '):
                        material_name = line.strip().split()[-1]
                        if material_name not in processed_materials:
                            processed_materials.add(material_name)
                            current_section.append(line)
                        else:
                            print(f"Skipping duplicate material: {material_name}")
                            current_section = []  # Skip this material block
                    elif current_section or (line.strip() and not line.startswith('#')):
                        current_section.append(line)
                    elif current_section:
                        all_converted_content.extend(current_section)
                        current_section = []
                        
                # Add any remaining content
                if current_section:
                    all_converted_content.extend(current_section)
                    
            except FileNotFoundError:
                print(f"Error: MTL file not found at {mtl_path}")
                continue
            except Exception as e:
                print(f"An error occurred processing {mtl_path}: {e}")
                continue
        
        # Create combined output file name
        if self.mtl_file_paths:
            self.combined_radiance_mtl_path = os.path.join(self.output_dir, "combined_radiance.mtl")
            
            # Write the combined output
            try:
                with open(self.combined_radiance_mtl_path, "w") as output_file:
                    output_file.write("\n".join(all_converted_content))
                print(f"Combined Radiance material file created: {self.combined_radiance_mtl_path}")
                print(f"Processed {len(processed_materials)} unique materials")
                
                # Add missing modifiers from all RAD files
                if self.combined_rad_paths:
                    self._add_missing_modifiers_from_all_rads()
                    
            except Exception as e:
                print(f"Error writing combined material file: {e}")

    def _rad_to_octree(self) -> None:
        """
        Runs the oconv command to generate frozen skyless octree for rendering from all RAD files.
        Output is placed in the same directory as the RAD/MTL files with fixed name 'combined_scene_skyless.oct'.
        Must use command prompt instead of powershell in VScode as its default encoding is utf-8
        instead of the required encoding for oconv.
        Example command: oconv -f material_file.mtl file1.rad file2.rad > output.oct
        """
        if not self.combined_rad_paths or not self.combined_radiance_mtl_path:
            print("No RAD files or material file available for octree generation")
            return
        
        # Determine output directory from the combined material file location
        output_filename = os.path.join(self.output_dir, "combined_scene_skyless.oct")
        
        # Build command with material file and all RAD files
        command = rf"oconv -f{self.combined_radiance_mtl_path} {self.combined_rad_paths} > {output_filename}"
        


        print(f"Generating octree from {len(self.combined_rad_paths)} RAD files...")

        run_commands_parallel(commands = command)
        
        try:
            with open(output_filename, "w") as outfile:
                process = subprocess.Popen(command, stdout=outfile, stderr=subprocess.PIPE)
                _, stderr = process.communicate()

            if stderr:
                print(f"Error running oconv: {stderr.decode()}")
            else:
                print(f"Successfully generated: {output_filename}")
        except Exception as e:
            print(f"Error generating octree: {e}")

    def create_skyless_octree_for_sunlight_analysis(self) -> None:
        """
        Process all OBJ/MTL file pairs: convert OBJ to RAD, parse MTL to Radiance format,
        and add missing modifiers. This is the main method to call for multi-file processing.
        """
        if not self.obj_file_paths or not self.mtl_file_paths:
            print("No files to process")
            return
            
        print(f"Processing {len(self.obj_file_paths)} OBJ/MTL file pairs...")
        
        # Convert all OBJ files to RAD
        self._obj_files_to_rad()
        
        # Parse and combine all MTL files
        self._parse_mtl_files()
        
        # Combine all rad file and mtl files converted to radiance description files into one octree
        self._rad_to_octree()

