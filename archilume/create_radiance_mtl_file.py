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
import archilume.radiance_materials as rm

# Standard library imports
import os
import re
from dataclasses import dataclass, field
import pathlib as Path

# Third-party imports
import pyradiance as pr

@dataclass
class CreateRadianceMtlFile:
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
        self.output_dir = os.path.join(os.path.dirname(__file__), "..", "intermediates", "rad")
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        # Extract modifiers from RAD files to create a list of primitives
        if self.rad_paths:
            for rad_file_path in self.rad_paths:
                modifiers = self._extract_modifiers_from_rad(rad_file_path)
                self.rad_modifiers.update(modifiers)

            print("Found modifiers:", self.rad_modifiers)

        # create output mtl file path
        self.output_mtl_path = os.path.join(self.output_dir, "materials.mtl")
    
    @staticmethod
    def _extract_modifiers_manually(rad_file_path) -> set[str]:
        """
        Extract modifiers from a RAD file by parsing line by line.
        Modifiers appear immediately after blank lines.
        
        Args:
            rad_file_path (str): Path to the RAD file
            
        Returns:
            set: Set of modifier names found in the file
        """
        modifiers = set()
        
        with open(rad_file_path, 'r') as file:
            lines = file.readlines()
        
        prev_line_blank = False
        
        for line in lines:
            stripped_line = line.strip()
            
            # Check if current line is blank
            if not stripped_line:
                prev_line_blank = True
                continue
            
            # Skip comments
            if stripped_line.startswith('#'):
                continue
            
            # If previous line was blank, this could be a modifier line
            if prev_line_blank:
                parts = stripped_line.split()
                
                # Check if line has enough parts to be a modifier definition
                if len(parts) >= 3:
                    modifier_name = parts[0]
                    primitive_type = parts[1]
                    identifier = parts[2]
                    
                    # Add modifier name if it's not 'void' (geometry uses modifiers)
                    if modifier_name != 'void':
                        modifiers.add(modifier_name)
                    
                    # Add identifier if this is a modifier definition
                    if primitive_type in ['plastic', 'glass', 'metal', 'trans', 'light', 'glow', 'texfunc', 'colorpict', 'brightfunc']:
                        modifiers.add(identifier)
            
            prev_line_blank = False
        
        return modifiers

    def _extract_modifiers_from_rad(self, rad_file_path) -> set[str]:
        """
        Extract all modifiers from a RAD file using pyradiance.
        example command: !getprimitives input.rad | getinfo -d
        """

        # Read the RAD file content
        with open(rad_file_path, 'r') as file:
            rad_content = file.read()

        # Parse primitives from the content
        primitives = pr.parse_primitive(rad_content)

        # Extract unique modifiers
        modifiers = set()

        for primitive in primitives:
            # Add the modifier name if it exists and isn't 'void'
            if primitive.modifier and primitive.modifier != 'void':
                modifiers.add(primitive.modifier)

            # If this primitive itself is a modifier, add its identifier
            if primitive.ptype in ['plastic', 'glass', 'metal', 'trans', 'light', 'glow']:
                modifiers.add(primitive.identifier)

        manual_modifiers = self._extract_modifiers_manually(rad_file_path)
        modifiers.update(manual_modifiers)
        #TODO: working on this here.

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
                        #FIXME: somehow materials here that are not in the mtl files are not being appended to the final mtl file.Determine why this is e.g. "Material_not_defined" is not being added to the final mtl file.

            # Export to file
            rm.export_materials_to_file(self.materials, self.output_mtl_path)     








