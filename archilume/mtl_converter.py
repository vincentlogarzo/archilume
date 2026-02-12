# Archilume imports
from archilume import radiance_materials as rm

# Standard library imports
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
import subprocess

# Third-party imports
import pyradiance as pr

# Material default constants
DEFAULT_MATERIAL_KD = [0.5, 0.5, 0.5]  # Medium gray for default materials
DEFAULT_OPACITY = 1.0  # Fully opaque by default

@dataclass
class MtlConverter:
    """
    Processes a Radiance .rad file and an accompanying .mtl file to find
    modifiers defined in the .rad file that are missing from the .mtl file,
    and appends default definitions for them.
    """
    
    # Input file paths
    rad_paths: list[str] = field(default_factory=list)
    mtl_paths: list[str] = field(default_factory=list)
    
    # Internal state
    rad_modifiers: set[str] = field(init=False, default_factory=set)
    output_mtl_path: str = field(init=False)
    materials = []

    def __post_init__(self):
        """Initializes the output directory for Radiance material files."""
        
        # Ensure output directory exists
        self.output_dir = Path(__file__).parent.parent / "outputs" / "rad"
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        # Extract modifiers from RAD files to create a list of primitives
        if self.rad_paths:
            for rad_file_path in self.rad_paths:
                modifiers = self.__get_modifiers_from_rad(Path(rad_file_path))
                self.rad_modifiers.update(modifiers)

            print("Found modifiers:", self.rad_modifiers)

        # create output mtl file path
        self.output_mtl_path = os.path.join(self.output_dir, "materials.mtl")
    
    def __get_modifiers_from_rad(self, rad_file_path: Path) -> set[str]:
        """
        Extract modifier names from RAD file using rad2mgf.
        This can alternatively be performed with: obj2rad -n Untitled.obj > a.mat
        example 1: obj2rad -n C:/Projects/archilume/inputs/87cowles_BLD_noWindows.obj > C:/Projects/archilume/outputs/rad/87cowles_BLD_noWindows.mat
        rad2mgf was more effective and thus implmented below. 
        """
        
        if not rad_file_path.exists():
            print(f"Error: RAD file not found: {rad_file_path}")
            return set()

        # Run rad2mgf and capture output
        try:
            result = subprocess.run(
                ['rad2mgf', str(rad_file_path)],
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
        except FileNotFoundError:
            print("Error: rad2mgf command not found. Make sure Radiance is installed.")
            return set()

        if result.returncode != 0:
            print(f"Error running rad2mgf: {result.stderr}")
            return set()

        # Filter lines starting with 'm' and extract modifier names
        modifiers = set()
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith('m '):
                # Extract modifier name (typically the second token)
                parts = line.split()
                if len(parts) > 1:
                    modifiers.add(parts[1])
        
        return modifiers

    def create_radiance_mtl_file(self):
        """
        Generates a Radiance .mtl file containing material definitions for all modifiers found in the RAD files.
        This method performs the following steps:
        1. Iterates through each modifier extracted from RAD files.
        2. Searches for corresponding material definitions in provided .mtl files.
        3. If a modifier is found in an .mtl file, extracts its properties (such as RGB diffuse color and transparency).
        4. Determines the appropriate Radiance material type (glass or plastic) based on transparency.
        5. Appends the generated Radiance material definition to the materials list.
        6. Exports all collected material definitions to the output .mtl file.
        Notes:
            - If a modifier is not found in any .mtl file, a default gray plastic material is created for it.
            - Future enhancements may include more detailed material property extraction (e.g., specular, roughness, metalness).
        """
        # Step 1: extract modifiers from rad files using the pyradiance library
            # handled by __post_init__

        # Step 2: check each modifier against the mtl files, if not found, then append a default definition to the combined_mtl file. IF found, then determine the RGB and other modifier properties to create a new radiance material definition. 

        materials_from_mtl = 0
        default_materials = 0

        for modifier in self.rad_modifiers:
            material_found = False

            # Search for modifier in all MTL files
            for mtl_path in self.mtl_paths:
                if not os.path.exists(mtl_path):
                    continue

                with open(mtl_path, 'r', encoding='utf-8') as f:
                    mtl_content = f.read()
                    # Use regex to find the material definition
                    pattern = rf'newmtl\s+{re.escape(modifier)}(.*?)(?=^newmtl|\Z)'
                    match = re.search(pattern, mtl_content, re.MULTILINE | re.DOTALL)

                    if match:
                        material_found = True
                        material_block = match.group(1)

                        # Extract Kd values (RGB diffuse color)
                        kd_values = DEFAULT_MATERIAL_KD
                        kd_match = re.search(r'Kd\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)', material_block)
                        if kd_match:
                            kd_values = [float(kd_match.group(1)), float(kd_match.group(2)), float(kd_match.group(3))]

                        # Extract d value (transparency/dissolve)
                        d_value = DEFAULT_OPACITY
                        d_match = re.search(r'^d\s+([\d.]+)', material_block, re.MULTILINE)
                        if d_match:
                            d_value = float(d_match.group(1))

                        if d_value < 1.0:
                            # It's a glass-like material
                            self.materials.append(rm.create_glass_material(f"{modifier}", kd_values))
                        else:
                            # It's a plastic-like material
                            self.materials.append(rm.create_plastic_material(f"{modifier}", kd_values))

                        materials_from_mtl += 1
                        break  # Found the material, no need to check other MTL files

                        #TODO: further logic could be added here in the future to provide greater accuracy to material definitions, such as checking for specular highlights, roughness, metalness, etc.

            # If no match found in any MTL file, create a default material
            if not material_found:
                # Create a default gray plastic material for unmatched modifiers
                self.materials.append(rm.create_plastic_material(f"{modifier}", DEFAULT_MATERIAL_KD))
                default_materials += 1

        # Print summary
        print(f"Created {materials_from_mtl} materials from MTL file" + (f" and {default_materials} default materials" if default_materials > 0 else ""))

        # Export to file (after processing all modifiers)
        rm.export_materials_to_file(self.materials, self.output_mtl_path)











