from pathlib import Path


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
    input_path = Path(__file__).parent.parent / "inputs" / "87cowles_BLD_noWindows.obj"
    output_path = Path(__file__).parent.parent / "inputs" / f"{input_path.stem}_simplified.obj"

    # Use the string-based approach (more reliable for complex OBJ files)
    simplify_obj(
        input_path=input_path,
        output_path=output_path
    )

    # Note: simplify_obj_pywavefront() may fail on OBJ files with:
    # - Missing material definitions
    # - Group statements
    # - Complex BIM/CAD exports