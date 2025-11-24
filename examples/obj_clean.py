from pathlib import Path
import open3d as o3d


def simplify_mesh_open3d(input_path, output_path, target_triangle_ratio=0.1):
    """
    Simplify an OBJ file by reducing triangle count using Open3D's quadric decimation.
    This merges coplanar triangles and reduces mesh complexity while preserving shape.

    Args:
        input_path: Path to input OBJ file
        output_path: Path to output simplified OBJ file
        target_triangle_ratio: Target ratio of triangles (0.1 = reduce to 10% of original)
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    # Create output directory if it doesn't exist
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading mesh from {input_path}...")
    mesh = o3d.io.read_triangle_mesh(str(input_path))

    original_triangles = len(mesh.triangles)
    original_vertices = len(mesh.vertices)

    if original_triangles == 0:
        print(f"Error: No triangles found in {input_path}")
        print("The OBJ file may have complex material groups that Open3D cannot parse.")
        print("Try using simplify_obj() to strip texture references first.")
        return

    target_triangles = int(original_triangles * target_triangle_ratio)

    print(f"Original: {original_vertices:,} vertices, {original_triangles:,} triangles")
    print(f"Target: {target_triangles:,} triangles ({target_triangle_ratio*100:.1f}%)")
    print("Simplifying mesh using quadric decimation...")

    # Quadric decimation - preserves shape while reducing triangles
    simplified_mesh = mesh.simplify_quadric_decimation(target_number_of_triangles=target_triangles)

    final_triangles = len(simplified_mesh.triangles)
    final_vertices = len(simplified_mesh.vertices)
    print(f"Final: {final_vertices:,} vertices, {final_triangles:,} triangles")
    print(f"Reduction: {original_triangles - final_triangles:,} triangles removed ({(1-final_triangles/original_triangles)*100:.1f}%)")

    # Save simplified mesh - write faces properly
    print(f"Writing simplified mesh to {output_path}...")
    o3d.io.write_triangle_mesh(str(output_path), simplified_mesh, write_ascii=True, write_vertex_normals=False, write_vertex_colors=False)

    # Verify the output has faces
    with open(output_path, 'r') as f:
        has_faces = any(line.startswith('f ') for line in f)

    if has_faces:
        print(f"✓ Simplified mesh written to: {output_path}")
    else:
        print(f"✗ Warning: Output file may be invalid (no faces found)")
        print("  Try using simplify_obj() instead to preserve the original structure.")

def simplify_obj(input_path, output_path):
    """
    Simplify an OBJ file by keeping only vertices and faces,
    and stripping texture/normal references from faces.

    Args:
        input_path: Path to input OBJ file
        output_path: Path to output simplified OBJ file
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    # Create output directory if it doesn't exist
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(input_path, "r") as infile:
        with open(output_path, "w") as outfile:
            for line in infile:
                # Only keep vertices and faces
                if line.startswith(("v ", "f ", "o ", "g ", "usemtl ")):
                    # For faces, strip texture/normal references
                    if line.startswith("f "):
                        parts = line.split()
                        simplified = "f " + " ".join([p.split("/")[0] for p in parts[1:]]) + "\n"
                        outfile.write(simplified)
                    else:
                        outfile.write(line)

    print(f"Simplified OBJ written to: {output_path}")


if __name__ == "__main__":
    # Example usage
    input_path = Path(__file__).parent.parent / "inputs" / "22041_AR_T01_BLD_hiddenLine.obj"

    # IMPORTANT: For Radiance sunlight analysis, decimation is NOT recommended because:
    # 1. Material assignments are lost (glass, walls, etc. become indistinguishable)
    # 2. Small features like windows may be simplified away
    # 3. Affects shadow accuracy and light transmission calculations
    
    # RECOMMENDED: Only strip texture/normal references (preserves all geometry + materials)

    print("=" * 60)
    print("Cleaning OBJ file (removing texture/normal references)")
    print("Materials and geometry preserved for accurate Radiance analysis")
    print("=" * 60)
    output_path = Path(__file__).parent.parent / "inputs" / f"{input_path.stem}_cleaned.obj"
    simplify_obj(input_path=input_path, output_path=output_path)

    # OPTIONAL: Decimation (NOT RECOMMENDED for Radiance analysis)
    # Uncomment below only if file is too large AND you don't need material accuracy
    """
    print("\n" + "=" * 60)
    print("WARNING: Decimating mesh (materials will be lost!)")
    print("=" * 60)
    decimated_path = Path(__file__).parent.parent / "inputs" / f"{input_path.stem}_decimated.obj"
    simplify_mesh_open3d(
        input_path=output_path,
        output_path=decimated_path,
        target_triangle_ratio=0.5  # Conservative 50% for analysis
    )
    """