"""
.mtl file needs to be in utf-8 encoding.

# black_plastic
void plastic black_plastic
0
0,
5 0.0 0.0 0.0 0.0 0.05

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

basic_materials = textwrap.dedent('\
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
    ')

"""
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

@dataclass
class Convert2RadianceMtlFile:
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
        self.output_dir = Path(__file__).parent.parent / "intermediates" / "rad"
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        # Extract modifiers from RAD files to create a list of primitives
        if self.rad_paths:
            for rad_file_path in self.rad_paths:
                modifiers = self._get_modifiers_from_rad(rad_file_path)
                self.rad_modifiers.update(modifiers)

            print("Found modifiers:", self.rad_modifiers)

        # create output mtl file path
        self.output_mtl_path = os.path.join(self.output_dir, "materials.mtl")
    
    def _get_modifiers_from_rad(self, rad_file_path: Path) -> set[str]:
        """Extract modifier names from RAD file using rad2mgf."""
        
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
        """Creates a Radiance .mtl file with definitions for all modifiers found in the RAD files."""
        # Step 1: extract modifiers from rad files using the pyradiance library
            # handled by __post_init__

        # Step 2: check each modifier against the mtl files, if not found, then append a default definition to the combined_mtl file. IF found, then determine the RGB and other modifier properties to create a new radiance material definition. 

        for modifier in self.rad_modifiers:
            for mtl_path in self.mtl_paths:
                if not os.path.exists(mtl_path):
                    continue
                with open(mtl_path, 'r', encoding='utf-8') as f:
                    mtl_content = f.read()
                    # Use regex to find the material definition
                    pattern = rf'newmtl\s+{re.escape(modifier)}(.*?)(?=^newmtl|\Z)'
                    match = re.search(pattern, mtl_content, re.MULTILINE | re.DOTALL)
                    
                    if match:

                    #FIXME: if there is no match, the material modifier if passed and not entered into the mtl file with a radince description. This may mean that the original pyradiance primitive call may have worked, it was just this code that passed over the modifiers not already found in the .mtl files from revit.
                        material_block = match.group(1)
                        
                        # Extract Kd values (RGB diffuse color)
                        kd_match = re.search(r'Kd\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)', material_block)
                        if kd_match:
                            kd_values = [float(kd_match.group(1)), float(kd_match.group(2)), float(kd_match.group(3))]
                        
                        # Extract d value (transparency/dissolve)
                        d_match = re.search(r'^d\s+([\d.]+)', material_block, re.MULTILINE)
                        if d_match:
                            d_value = float(d_match.group(1))
                    
                        if d_value < 1.0:
                            # It's a glass-like material
                            self.materials.append(rm.create_glass_material(f"{modifier}", kd_values))
                        else:
                            # It's a plastic-like material
                            self.materials.append(rm.create_plastic_material(f"{modifier}", kd_values))

                        #TODO: futher logic could be added here in the futrue to provide greater accuracy to material definitions, such as checking for specular highlights, roughness, metalness, etc.

            # Export to file
            rm.export_materials_to_file(self.materials, self.output_mtl_path)     








