"""Clean up the outputs folder to prepare for fresh rendering."""

import shutil
from pathlib import Path


def clear_outputs_folder(retain_amb_files: bool = False) -> None:
    """
    Remove all files from the outputs folder.

    Args:
        retain_amb_files: If True, keeps .amb files in the images directory.
                         If False, removes everything.
    """
    outputs_dir = Path(__file__).parent / "outputs"

    if not outputs_dir.exists():
        print(f"Outputs directory does not exist: {outputs_dir}")
        return

    # Remove all contents
    for item in outputs_dir.iterdir():
        if item.is_file():
            item.unlink()
            print(f"Removed file: {item.name}")
        elif item.is_dir():
            # Handle images directory specially if retaining .amb files
            if retain_amb_files and item.name == "images":
                for file in item.iterdir():
                    if file.is_file() and file.suffix != ".amb":
                        file.unlink()
                        print(f"Removed file: images/{file.name}")
                    elif file.is_dir():
                        shutil.rmtree(file)
                        print(f"Removed directory: images/{file.name}")
                # Remove images dir if empty (no .amb files were present)
                if not any(item.iterdir()):
                    item.rmdir()
                    print(f"Removed empty directory: {item.name}")
            else:
                shutil.rmtree(item)
                print(f"Removed directory: {item.name}")

    print("Outputs folder cleanup complete.")


if __name__ == "__main__":
    # Set to True to keep .amb files in images directory
    clear_outputs_folder(retain_amb_files=True)
