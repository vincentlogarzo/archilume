"""
Generate level-by-level room boundaries CSV from an OBJ file.

Parses the OBJ file to extract bounding box extents, then creates
rectangular room boundaries for each level at specified intervals.
"""

import csv
import os
from pathlib import Path


def parse_obj_bounding_box(filepath: Path) -> dict:
    """
    Parse an OBJ file and extract bounding box information.

    Args:
        filepath: Path to the OBJ file

    Returns:
        Dictionary containing bounding box min/max coordinates and statistics
    """
    # Get file size
    file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
    print(f"Parsing OBJ file: {filepath.name}")
    print(f"File size: {file_size_mb:.2f} MB\n")

    # Count different element types
    vertices = 0
    faces = 0
    normals = 0
    textures = 0
    objects = 0
    groups = 0
    materials = 0
    lines_total = 0

    # Bounding box tracking
    min_x = min_y = min_z = float("inf")
    max_x = max_y = max_z = float("-inf")

    object_faces = {}
    current_object = "unnamed"

    with open(filepath, "r") as f:
        for line in f:
            lines_total += 1
            if line.startswith("v "):
                vertices += 1
                # Parse vertex coordinates for bounding box
                parts = line.split()
                if len(parts) >= 4:
                    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                    min_x = min(min_x, x)
                    max_x = max(max_x, x)
                    min_y = min(min_y, y)
                    max_y = max(max_y, y)
                    min_z = min(min_z, z)
                    max_z = max(max_z, z)
            elif line.startswith("f "):
                faces += 1
                object_faces[current_object] = object_faces.get(current_object, 0) + 1
            elif line.startswith("vn "):
                normals += 1
            elif line.startswith("vt "):
                textures += 1
            elif line.startswith("o "):
                objects += 1
                current_object = line.strip()[2:]
                if current_object not in object_faces:
                    object_faces[current_object] = 0
            elif line.startswith("g "):
                groups += 1
            elif line.startswith("usemtl "):
                materials += 1

    print(f"Total lines: {lines_total:,}")
    print(f"Vertices: {vertices:,}")
    print(f"Faces: {faces:,}")
    print(f"Normals: {normals:,}")
    print(f"Texture coords: {textures:,}")
    print(f"Objects: {objects:,}")
    print(f"Groups: {groups:,}")
    print(f"Material switches: {materials:,}\n")

    # Bounding box information
    if vertices > 0:
        width = max_x - min_x
        height = max_y - min_y
        depth = max_z - min_z
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        center_z = (min_z + max_z) / 2

        print("Bounding Box:")
        print(f"  X: {min_x:.3f} to {max_x:.3f} (width: {width:.3f})")
        print(f"  Y: {min_y:.3f} to {max_y:.3f} (height: {height:.3f})")
        print(f"  Z: {min_z:.3f} to {max_z:.3f} (depth: {depth:.3f})")
        print(f"  Center: ({center_x:.3f}, {center_y:.3f}, {center_z:.3f})\n")

        # Top objects by face count
        print("Top 20 objects by face count:")
        sorted_objects = sorted(object_faces.items(), key=lambda x: x[1], reverse=True)
        for obj_name, count in sorted_objects[:20]:
            pct = (count / faces * 100) if faces > 0 else 0
            print(f"{count:8,} faces ({pct:5.1f}%): {obj_name}")
        print()

        return {
            "x_min": min_x,
            "x_max": max_x,
            "y_min": min_y,
            "y_max": max_y,
            "z_min": min_z,
            "z_max": max_z,
            "width": width,
            "height": height,
            "depth": depth,
            "center": (center_x, center_y, center_z),
            "vertices": vertices,
            "faces": faces,
        }

    raise ValueError("No vertices found in OBJ file")

def generate_room_boundaries(
    bbox: dict,
    level_height: float = 3.0,
    output_path: str = "room_boundaries.csv",
    room_type: str = "FLOOR",
    level_prefix: str = "L",
    coordinate_scale: float = 1000.0,
) -> list:
    """
    Generate room boundaries CSV file from bounding box.

    Args:
        bbox: Dictionary with x_min, x_max, y_min, y_max, z_min, z_max
        level_height: Height interval between levels (meters)
        output_path: Output CSV file path
        room_type: Room type label for each boundary
        level_prefix: Prefix for level IDs (e.g., "L" for L01, L02, etc.)
        coordinate_scale: Scale factor for coordinates (1000 = mm, 1 = m)

    Returns:
        List of generated rows
    """
    x_min = bbox["x_min"]
    x_max = bbox["x_max"]
    y_min = bbox["y_min"]
    y_max = bbox["y_max"]
    z_min = bbox["z_min"]
    z_max = bbox["z_max"]

    # Calculate level Z heights
    z_heights = []
    z = z_min
    while z <= z_max:
        z_heights.append(z)
        z += level_height

    # Scale coordinates
    x_min_scaled = x_min * coordinate_scale
    x_max_scaled = x_max * coordinate_scale
    y_min_scaled = y_min * coordinate_scale
    y_max_scaled = y_max * coordinate_scale

    # Generate rows
    rows = []
    for i, z in enumerate(z_heights, start=1):
        z_scaled = z * coordinate_scale

        # Create level ID with zero-padded number
        level_id = f"{level_prefix}{i:02d}"

        # Define 4 corner points (clockwise from bottom-left)
        points = [
            f"X_{x_min_scaled:.3f} Y_{y_min_scaled:.3f} Z_{z_scaled:.3f}",
            f"X_{x_max_scaled:.3f} Y_{y_min_scaled:.3f} Z_{z_scaled:.3f}",
            f"X_{x_max_scaled:.3f} Y_{y_max_scaled:.3f} Z_{z_scaled:.3f}",
            f"X_{x_min_scaled:.3f} Y_{y_max_scaled:.3f} Z_{z_scaled:.3f}",
        ]

        # Pad with empty columns to match template format (28 columns total)
        while len(points) < 26:
            points.append("")

        row = [level_id, room_type] + points
        rows.append(row)

    # Write CSV
    output_file = Path(output_path)
    with open(output_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    print(f"Generated {len(rows)} levels from Z={z_min:.3f}m to Z={z_heights[-1]:.3f}m")
    print(f"Output saved to: {output_file.absolute()}")

    return rows

def main(
    obj_filepath: Path,
    output_path: str = None,
    level_height: float = 3.0,
    room_type: str = "FLOOR",
    level_prefix: str = "L",
    coordinate_scale: float = 1000.0,
):
    """
    Main function to parse OBJ and generate room boundaries CSV.

    Args:
        obj_filepath: Path to input OBJ file
        output_path: Output CSV path (default: derived from OBJ filename)
        level_height: Height interval between levels (meters)
        room_type: Room type label for each boundary
        level_prefix: Prefix for level IDs
        coordinate_scale: Scale factor for coordinates (1000 = mm)
    """
    obj_path = Path(obj_filepath)

    if not obj_path.exists():
        raise FileNotFoundError(f"OBJ file not found: {obj_path}")

    # Default output path in same directory as OBJ file
    if output_path is None:
        output_path = obj_path.parent / f"{obj_path.stem}_room_boundaries.csv"

    # Parse OBJ file for bounding box
    bbox = parse_obj_bounding_box(obj_path)

    # Generate room boundaries
    generate_room_boundaries(
        bbox=bbox,
        level_height=level_height,
        output_path=output_path,
        room_type=room_type,
        level_prefix=level_prefix,
        coordinate_scale=coordinate_scale,
    )


if __name__ == "__main__":
    # Configuration variables for faster prototyping
    obj_file            = Path(__file__).parent.parent / "inputs" / "22041_AR_T01_v2.obj"
    output_csv          = None      # Auto-generate from obj filename
    level_height        = 3.0       # Height interval between levels (meters)
    room_type           = "FLOOR"   # Room type label
    level_prefix        = "L"       # Level ID prefix (L01, L02, etc.)
    coordinate_scale    = 1000.0    # Scale factor (1000 = mm, 1 = m)

    main(
        obj_filepath=obj_file,
        output_path=output_csv,
        level_height=level_height,
        room_type=room_type,
        level_prefix=level_prefix,
        coordinate_scale=coordinate_scale,
    )