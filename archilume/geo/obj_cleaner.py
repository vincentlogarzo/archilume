"""
OBJ File Cleaner for Radiance Sunlight Simulations

Strips unnecessary data from OBJ files for Radiance daylight simulation. Removes vertex normals (vn), texture coordinates (vt), face UV/normal references, smoothing groups (s), mtllib declarations, and comments — none of which affect Radiance light transport. Radiance computes surface normals internally and materials are supplied directly to the renderer, not via the OBJ mtllib pointer.

Keeps: vertices (v), faces (f), object names (o), groups (g), material assignments (usemtl)

Workflow:
1. Decimate mesh in Blender (Modifiers > Decimate, ratio 0.1-0.5)
2. Run this script to clean the OBJ file

Output: Creates a new file with '_cleaned' suffix (original preserved)
"""

from pathlib import Path
from archilume import config


def clean_obj_for_radiance(input_path, output_path=None, verbose=True):
    """
    Clean an OBJ file by removing all non-essential data for Radiance simulations.

    Keeps only:
    - Vertices (v)
    - Faces (f) with vertex indices only (strips texture/normal refs)
    - Object names (o)
    - Groups (g)
    - Material assignments (usemtl)

    Args:
        input_path: Path to input OBJ file
        output_path: Path to output file (defaults to input_path_cleaned.obj)
        verbose: Print statistics about cleaning process

    Returns:
        Path to the cleaned output file
    """
    input_path = Path(input_path)

    if output_path is None:
        output_path = input_path.parent / f"{input_path.stem}_cleaned.obj"
    else:
        output_path = Path(output_path)

    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Statistics tracking
    stats = {
        'vertices_in': 0,
        'vertices_out': 0,
        'faces_in': 0,
        'faces_out': 0,
        'normals_removed': 0,
        'textures_removed': 0,
        'lines_in': 0,
        'lines_out': 0,
        'objects': 0,
        'groups': 0,
        'materials': 0,
    }

    with open(input_path, 'r') as infile:
        with open(output_path, 'w') as outfile:
            # Write header
            outfile.write(f"# OBJ file cleaned for Radiance by Archilume\n")
            outfile.write(f"# Source: {input_path.name}\n\n")

            for line in infile:
                stats['lines_in'] += 1
                stripped = line.strip()

                # Skip empty lines and comments
                if not stripped or stripped.startswith('#'):
                    continue

                # Vertex - keep as-is
                if line.startswith('v '):
                    stats['vertices_in'] += 1
                    stats['vertices_out'] += 1
                    stats['lines_out'] += 1
                    outfile.write(line)

                # Face - strip texture/normal references
                elif line.startswith('f '):
                    stats['faces_in'] += 1
                    parts = line.split()
                    # Extract only vertex indices (before first /)
                    vertex_indices = [p.split('/')[0] for p in parts[1:]]
                    simplified_face = 'f ' + ' '.join(vertex_indices) + '\n'
                    stats['faces_out'] += 1
                    stats['lines_out'] += 1
                    outfile.write(simplified_face)

                # Object name - keep
                elif line.startswith('o '):
                    stats['objects'] += 1
                    stats['lines_out'] += 1
                    outfile.write(line)

                # Group - keep
                elif line.startswith('g '):
                    stats['groups'] += 1
                    stats['lines_out'] += 1
                    outfile.write(line)

                # Material assignment - keep
                elif line.startswith('usemtl '):
                    stats['materials'] += 1
                    stats['lines_out'] += 1
                    outfile.write(line)

                # Vertex normal - skip (Radiance calculates automatically)
                elif line.startswith('vn '):
                    stats['normals_removed'] += 1

                # Texture coordinate - skip (not used in lighting)
                elif line.startswith('vt '):
                    stats['textures_removed'] += 1

                # Everything else - skip (mtllib, s, etc.)

    # Print statistics if requested
    if verbose:
        input_size = input_path.stat().st_size / 1024 / 1024  # MB
        output_size = output_path.stat().st_size / 1024 / 1024  # MB
        reduction = (1 - output_size / input_size) * 100 if input_size > 0 else 0

        print("\n" + "="*80)
        print(f"OBJ Cleaning Results: {input_path.name}")
        print("="*80)
        print(f"Input file:  {input_size:.2f} MB ({stats['lines_in']:,} lines)")
        print(f"Output file: {output_size:.2f} MB ({stats['lines_out']:,} lines)")
        print(f"Reduction:   {reduction:.1f}%\n")

        print("Geometry:")
        print(f"  Vertices: {stats['vertices_out']:,}")
        print(f"  Faces:    {stats['faces_out']:,}")
        print(f"  Objects:  {stats['objects']:,}")
        print(f"  Groups:   {stats['groups']:,}")
        print(f"  Materials: {stats['materials']:,}\n")

        print("Removed:")
        print(f"  Vertex normals:      {stats['normals_removed']:,}")
        print(f"  Texture coordinates: {stats['textures_removed']:,}")
        print(f"  Comments/metadata:   {stats['lines_in'] - stats['lines_out'] - stats['normals_removed'] - stats['textures_removed']:,}")
        print("="*80)
        print(f"\nCleaned file saved to: {output_path}\n")

    return output_path

if __name__ == "__main__":
    # Example usage - modify the input path to your OBJ file
    input_file = config.INPUTS_DIR / "527DM" / "223181_AR_LOFTUS_BTR_cleaned_stripped_cleaned.obj"

    # Clean the file
    output_file = clean_obj_for_radiance(
        input_path=input_file,
        verbose=True
    )
