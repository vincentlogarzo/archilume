"""Clean the images directory by removing all files.
to run enter python examples/clean_images_folder.py --force
"""

import shutil
from pathlib import Path


def clean_images_directory(images_path: str = None, dry_run: bool = False) -> None:
    """
    Remove all files from the images directory.

    Args:
        images_path: Path to the images directory. If None, uses default outputs/images.
        dry_run: If True, only print what would be deleted without actually deleting.
    """
    # Default to outputs/images relative to project root
    if images_path is None:
        project_root = Path(__file__).parent.parent
        images_dir = project_root / "outputs" / "images"
    else:
        images_dir = Path(images_path)

    if not images_dir.exists():
        print(f"Images directory does not exist: {images_dir}")
        return

    if not images_dir.is_dir():
        print(f"Path is not a directory: {images_dir}")
        return

    # Count files
    all_files = list(images_dir.iterdir())
    file_count = sum(1 for item in all_files if item.is_file())
    dir_count = sum(1 for item in all_files if item.is_dir())

    print(
        f"Found {file_count} files and {dir_count} directories in {images_dir}")

    if dry_run:
        print("\n[DRY RUN] Would delete the following:")
        for item in all_files:
            if item.is_file():
                print(f"  File: {item.name} ({item.stat().st_size} bytes)")
            elif item.is_dir():
                print(f"  Directory: {item.name}/")
        print("\nRun with dry_run=False to actually delete these files.")
        return

    # Actually delete
    deleted_files = 0
    deleted_dirs = 0

    for item in all_files:
        try:
            if item.is_file():
                item.unlink()
                deleted_files += 1
                print(f"Deleted file: {item.name}")
            elif item.is_dir():
                shutil.rmtree(item)
                deleted_dirs += 1
                print(f"Deleted directory: {item.name}/")
        except Exception as e:
            print(f"Error deleting {item.name}: {e}")

    print(f"\nCleanup complete!")
    print(f"  Deleted {deleted_files} files")
    print(f"  Deleted {deleted_dirs} directories")


if __name__ == "__main__":
    import sys

    # Check if --force flag is provided
    force = "--force" in sys.argv or "-f" in sys.argv

    if not force:
        # Run in dry-run mode first to see what would be deleted
        print("=== DRY RUN MODE ===")
        print("This will show what would be deleted without actually deleting.")
        print("Run with --force or -f flag to actually delete the files.\n")
        clean_images_directory(dry_run=True)
    else:
        # Actually delete the files
        print("=== DELETION MODE ===")
        print("This will permanently delete all files in the images directory.\n")

        # Confirm deletion
        response = input(
            "Are you sure you want to delete all files? (yes/no): ")
        if response.lower() in ["yes", "y"]:
            clean_images_directory(dry_run=False)
        else:
            print("Deletion cancelled.")
