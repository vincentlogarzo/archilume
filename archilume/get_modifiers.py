"""
>>> Basic usage: 
rad2mgf input.rad > output.mgf
>>> example 1: 
rad2mgf "C:\\Projects\\archilume\\intermediates\\rad\\87cowles_BLD_noWindows.rad" > "C:\\Projects\\archilume\\intermediates\\rad\\materials.mgf"

"""

import subprocess
import os
from pathlib import Path
import pyradiance as pr

def get_modifiers_from_rad(rad_file_path: Path) -> set[str]:
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

if __name__ == "__main__":
    rad_file_path = Path(__file__).parent.parent / "intermediates" / "rad" / "87cowles_BLD_noWindows.rad"
    modifiers = get_modifiers_from_rad(rad_file_path)
    
    if modifiers:
        print(f"Found {len(modifiers)} modifiers:")
        for modifier in sorted(modifiers):
            print(f"  - {modifier}")
    else:
        print("No modifiers found.")

