"""Clean up the outputs folder to prepare for fresh rendering."""

from pathlib import Path


def clear_outputs_folder(retain_amb_files: bool = False) -> None:
    """
    Remove all files from the outputs folder while preserving directory structure.

    Args:
        retain_amb_files: If True, keeps .amb files in the images directory.
                         If False, removes all files.
    """
    outputs_dir = Path(__file__).parent.parent / "outputs"

    if not outputs_dir.exists():
        print(f"Outputs directory does not exist: {outputs_dir}")
        return

    # Recursively remove files while preserving directories
    def clear_directory(directory: Path, keep_amb: bool = False):
        for item in directory.iterdir():
            if item.is_file():
                # Skip .amb files if retain_amb_files is True and we're in images directory
                if keep_amb and item.suffix == ".amb":
                    print(f"Retained: {item.relative_to(outputs_dir)}")
                    continue
                item.unlink()
                print(f"Removed: {item.relative_to(outputs_dir)}")
            elif item.is_dir():
                # Apply amb retention only to images directory
                should_keep_amb = retain_amb_files and item.name == "images"
                clear_directory(item, keep_amb=should_keep_amb)

    clear_directory(outputs_dir)
    print(f"\nOutputs folder cleanup complete. Directory structure preserved.")


if __name__ == "__main__":
    # Set to True to keep .amb files in images directory
    clear_outputs_folder(retain_amb_files=False)
