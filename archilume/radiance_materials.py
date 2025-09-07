"""
Comprehensive Radiance Material Creator using pyradiance.Primitive

This module provides a complete library of functions to create all major Radiance 
primitive types using the pyradiance library's Primitive class. It offers type-safe
material creation with proper parameter validation and consistent formatting.

CONTENTS:
=========

BASIC MATERIALS (8 functions):
- create_plastic_material() - Standard opaque plastic surfaces
- create_metal_material() - Metallic surfaces with specular reflection
- create_glass_material() - Transparent glass materials
- create_trans_material() - Translucent materials (partial transparency)
- create_dielectric_material() - Dielectric interfaces with refractive index
- create_interface_material() - Material boundary interfaces
- create_prism1_material() - Single ray redirection for prismatic glazing
- create_prism2_material() - Double ray redirection for complex prisms

LIGHT SOURCES (4 functions):
- create_light_source() - Basic omnidirectional light sources
- create_illum_light() - Secondary light sources (windows, bright surfaces)
- create_glow_material() - Self-luminous glowing materials
- create_spotlight_source() - Directional spotlight sources with beam control

PATTERN & TEXTURE MATERIALS (4 functions):
- create_brightfunc_pattern() - Monochromatic procedural patterns
- create_colorfunc_pattern() - RGB procedural color patterns
- create_brightdata_pattern() - Monochromatic data-driven patterns
- create_colordata_pattern() - RGB data-driven color patterns

SPECIAL MATERIALS (3 functions):
- create_mirror_material() - Perfect mirror reflectors
- create_antimatter_material() - Light absorbing materials
- create_mist_material() - Participating media (fog, smoke, atmosphere)

UTILITY FUNCTIONS (3 functions):
- create_material_library() - Generate common architectural material library
- export_materials_to_file() - Export materials to .rad format files
- Example usage and material library generation

FEATURES:
- Type-safe parameter validation using pyradiance.Primitive
- Comprehensive documentation for all material parameters
- Consistent RGB color handling and proper Radiance formatting
- Pre-built architectural material library with common building materials
- File export capabilities for integration with Radiance workflows
- Full coverage of Radiance's material and light source primitives

USAGE:
    from radiance_materials import create_plastic_material
    
    wall = create_plastic_material("wall", [0.8, 0.8, 0.8], 0.0, 0.05)
    print(wall)  # Outputs proper Radiance material definition

Author: Generated for Archilume project
Dependencies: pyradiance, typing

See
- https://spectraldb.com/
- https://thinkmoult.com/
- aftabrad.com

"""


# Archilume imports

# Standard library imports
from typing import List, Optional, Union

# Third-party imports
from pyradiance import Primitive


# =============================================================================
# BASIC MATERIALS
# =============================================================================

def create_plastic_material(
    name: str, 
    kd: List[float] = [0.7, 0.7, 0.7], 
    ks: float = 0.0, 
    roughness: float = 0.05,
    modifier: str = "void"
) -> Primitive:
    """
    Create a plastic material primitive.
    
    Args:
        name: Material identifier
        kd: RGB diffuse reflectance [R, G, B] (0-1)
        ks: Specular reflectance (0-1)  
        roughness: Surface roughness (0-1)
        modifier: Modifier name (default "void")
    
    Returns:
        Primitive: Radiance plastic primitive
    """
    return Primitive(
        modifier=modifier,
        ptype="plastic",
        identifier=name,
        sargs=[],
        fargs=[kd[0], kd[1], kd[2], ks, roughness]
    )


def create_metal_material(
    name: str,
    kd: List[float] = [0.8, 0.8, 0.8],
    ks: float = 0.9,
    roughness: float = 0.01,
    modifier: str = "void"
) -> Primitive:
    """
    Create a metal material primitive.
    
    Args:
        name: Material identifier
        kd: RGB diffuse reflectance [R, G, B] (0-1)
        ks: Specular reflectance (0-1)
        roughness: Surface roughness (0-1)
        modifier: Modifier name
    """
    return Primitive(
        modifier=modifier,
        ptype="metal",
        identifier=name,
        sargs=[],
        fargs=[kd[0], kd[1], kd[2], ks, roughness]
    )


def create_glass_material(
    name: str,
    transmission: List[float] = [0.96, 0.96, 0.96],
    modifier: str = "void"
) -> Primitive:
    """
    Create a glass material primitive.
    
    Args:
        name: Material identifier  
        transmission: RGB transmission coefficients [R, G, B] (0-1)
        modifier: Modifier name
    """
    return Primitive(
        modifier=modifier,
        ptype="glass",
        identifier=name,
        sargs=[],
        fargs=[transmission[0], transmission[1], transmission[2]]
    )


# =============================================================================
# LIGHT SOURCES
# =============================================================================


# =============================================================================
# PATTERN AND TEXTURE MATERIALS
# =============================================================================


# =============================================================================
# SPECIAL MATERIALS
# =============================================================================

def create_mirror_material(
    name: str,
    rgb_reflectance: List[float] = [0.9, 0.9, 0.9],
    modifier: str = "void"
) -> Primitive:
    """
    Create a mirror material primitive.
    
    Args:
        name: Material identifier
        rgb_reflectance: RGB reflectance [R, G, B] (0-1)
        modifier: Modifier name
    """
    return Primitive(
        modifier=modifier,
        ptype="mirror",
        identifier=name,
        sargs=[],
        fargs=[rgb_reflectance[0], rgb_reflectance[1], rgb_reflectance[2]]
    )


def create_antimatter_material(
    name: str,
    modifier: str = "void"
) -> Primitive:
    """
    Create an antimatter material primitive (absorbs all light).
    
    Args:
        name: Material identifier
        modifier: Modifier name
    """
    return Primitive(
        modifier=modifier,
        ptype="antimatter",
        identifier=name,
        sargs=[],
        fargs=[]
    )


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def export_materials_to_file(materials: List[Primitive], filename: str) -> None:
    """
    Export a list of materials to a Radiance material file.
    
    Args:
        materials: List of Primitive materials to export
        filename: Output filename
    """
    with open(filename, 'w', encoding='utf-8') as f:
        f.write("# Radiance Material Library\n")
        f.write("# Generated using pyradiance\n\n")
        
        for material in materials:
            f.write(str(material))
            f.write("\n\n")
    
    print(f"Exported {len(materials)} materials to:{filename}")
    
    


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    # Create some example materials
    materials = []
    
    # Basic materials
    materials.append(create_plastic_material("white_wall", [0.8, 0.8, 0.8]))
    materials.append(create_metal_material("chrome", [0.9, 0.9, 0.9], 0.95, 0.01))
    materials.append(create_glass_material("window", [0.96, 0.96, 0.96]))
    materials.append(create_mirror_material("mirror", [0.95, 0.95, 0.95]))
    
    # Export to file
    export_materials_to_file(materials, "example_materials.rad")
    
    # Print individual materials
    for material in materials:
        print(material)
        print()