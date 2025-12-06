"""
Clean up the outputs folder to prepare for fresh rendering.

QUICK START - Smart Cleanup
============================

Use smart_cleanup() before re-runs when parameters change:

Example 1: Only resolution changed
    from archilume import smart_cleanup
    smart_cleanup(resolution_changed=True)

Example 2: Timestep changed
    smart_cleanup(timestep_changed=True)

Example 3: Switched CPU ↔ GPU
    smart_cleanup(rendering_mode_changed=True)

Example 4: Quality preset changed
    smart_cleanup(rendering_quality_changed=True)

Example 5: Multiple changes
    smart_cleanup(timestep_changed=True, resolution_changed=True)

See examples/smart_cleanup_example.py for detailed usage.
"""

from pathlib import Path
from archilume import config

def clear_outputs_folder(retain_amb_files: bool = False, retain_octree: bool = False) -> None:
    """
    Remove all files from the outputs folder while preserving directory structure.

    Args:
        retain_amb_files: If True, keeps .amb files in the images directory.
                         If False, removes all files.
        retain_octree: If True, keeps the entire octree folder and its contents.
                      If False, removes octree files like other folders.
    """
    outputs_dir = config.OUTPUTS_DIR

    if not outputs_dir.exists():
        print(f"Outputs directory does not exist: {outputs_dir}")
        return

    # Recursively remove files while preserving directories
    def clear_directory(directory: Path, keep_amb: bool = False, skip_octree: bool = False):
        for item in directory.iterdir():
            # Skip entire octree directory if retain_octree is True
            if skip_octree and item.is_dir() and item.name == "octree":
                print(f"Retained: {item.relative_to(outputs_dir)}/ (entire folder)")
                continue

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
                clear_directory(item, keep_amb=should_keep_amb, skip_octree=False)

    clear_directory(outputs_dir, skip_octree=retain_octree)
    print(f"\nOutputs folder cleanup complete. Directory structure preserved.")


def smart_cleanup(
    timestep_changed: bool = False,
    resolution_changed: bool = False,
    rendering_mode_changed: bool = False,
    rendering_quality_changed: bool = False
) -> None:
    """
    Smart cleanup for re-runs based on what parameter changed.

    IMPORTANT: ALWAYS DELETED (regardless of flags):
        - All files in wpd/ directory (post-processed working plane data)
        - All .gif and .apng files in image/ directory (animations)
        - Reason: These are derived from renders and must ALWAYS be regenerated
        - This happens even when ALL flags are FALSE

    Set flags to TRUE for parameters that changed since last run:

    Args:
        timestep_changed (bool): Set to TRUE if timestep changed.
            - Deletes: All .sky files, all .oct files, and image files (except .amb)
            - Retains: .amb files (overcast indirect lighting calculations)
            - Reason: New timesteps = new sky files = new octrees needed
            - Ambient files can be reused (scene geometry unchanged)

        resolution_changed (bool): Set to TRUE if image_resolution changed.
            - Deletes: .hdr and .tiff files from image/ directory
            - Retains: .amb files, octree files, sky files, view files
            - Reason: Ambient files are 64x64 regardless of final resolution
            - Only final renders need regeneration

        rendering_mode_changed (bool): Set to TRUE if switched between 'cpu' and 'gpu'.
            - Deletes: Everything in image/ directory (including .amb files)
            - Retains: octree/, sky/, view/ directories
            - Reason: CPU and GPU may produce different ambient calculations
            - Better to regenerate for consistency

        rendering_quality_changed (bool): Set to TRUE if quality preset changed.
            - Deletes: Everything in image/ directory (including .amb files)
            - Retains: octree/, sky/, view/ directories
            - Reason: Quality changes affect -ad, -as, -ab parameters
            - Ambient files should match quality settings

    Examples:
        >>> # Only resolution changed from 1024 to 2048
        >>> smart_cleanup(resolution_changed=True)

        >>> # Changed timestep AND resolution
        >>> smart_cleanup(timestep_changed=True, resolution_changed=True)

        >>> # Switched from CPU to GPU rendering
        >>> smart_cleanup(rendering_mode_changed=True)

    Notes:
        - If multiple flags are TRUE, they are combined intelligently:
            * rendering_mode_changed or rendering_quality_changed ALWAYS deletes .amb files
            * timestep_changed deletes sky files and octrees
            * All flags respect the .amb deletion rule when quality/mode changed
        - If no flags are TRUE, only post-processed files are deleted (animations, wpd)
        - Priority order for scenarios: timestep > mode/quality > resolution
        - .amb files are ALWAYS deleted when rendering_mode_changed or rendering_quality_changed is TRUE
    """

    outputs_dir = config.OUTPUTS_DIR
    image_dir = config.IMAGE_DIR
    octree_dir = config.OCTREE_DIR
    wpd_dir = config.OUTPUTS_DIR / "wpd"  # Post-processed working plane data

    if not outputs_dir.exists():
        print(f"Outputs directory does not exist: {outputs_dir}")
        return

    files_removed = []
    files_retained = []

    # ALWAYS clean post-processed outputs (derived from renders, always need regeneration)
    # This happens REGARDLESS of parameter flags
    print("\n" + "="*80)
    print("SMART CLEANUP - Cleaning Post-Processed Outputs")
    print("="*80)
    print("Post-processed files (animations, wpd) are ALWAYS deleted")
    print("-" * 80)

    # Delete wpd directory contents
    if wpd_dir.exists():
        for wpd_file in wpd_dir.iterdir():
            if wpd_file.is_file():
                wpd_file.unlink()
                files_removed.append(f"wpd/{wpd_file.name}")

    # Delete animation files (.gif, .apng) from image directory
    if image_dir.exists():
        for anim_file in image_dir.glob("*.gif"):
            anim_file.unlink()
            files_removed.append(f"image/{anim_file.name}")
        for anim_file in image_dir.glob("*.apng"):
            anim_file.unlink()
            files_removed.append(f"image/{anim_file.name}")

    print(f"Removed {len([f for f in files_removed if 'wpd/' in f or f.endswith(('.gif', '.apng'))])} post-processed files")
    print("="*80 + "\n")

    # If nothing changed, stop here (only post-processed files were deleted)
    if not any([timestep_changed, resolution_changed, rendering_mode_changed, rendering_quality_changed]):
        print("="*80)
        print("PARAMETER CHANGE DETECTION")
        print("="*80)
        print("No rendering parameter changes detected.")
        print("Render outputs (.hdr, .tiff, .amb, octrees) will be reused.")
        print("="*80 + "\n")
        return

    print("="*80)
    print("PARAMETER CHANGE DETECTION")
    print("="*80)
    print(f"Timestep changed:          {timestep_changed}")
    print(f"Resolution changed:        {resolution_changed}")
    print(f"Rendering mode changed:    {rendering_mode_changed}")
    print(f"Rendering quality changed: {rendering_quality_changed}")
    print("="*80 + "\n")

    # Determine if .amb files should be deleted
    # .amb files must be regenerated when rendering mode or quality changes
    delete_amb_files = rendering_mode_changed or rendering_quality_changed

    # SCENARIO 1: Timestep changed
    # Delete sky files, octrees, and image outputs
    if timestep_changed:
        print("SCENARIO 1: Timestep changed")
        print("-" * 80)
        if delete_amb_files:
            print("Action: Delete sky/, octree/, and ALL image/ files (including .amb)")
            print("Reason: New timesteps + quality/mode change requires full regeneration\n")
        else:
            print("Action: Delete sky/, octree/, and image/ files, RETAIN .amb files")
            print("Reason: New timesteps require new sky files and octrees")
            print("        Ambient files can be reused (scene geometry unchanged)\n")

        # Delete sky files (new timesteps need new sky files)
        sky_dir = config.SKY_DIR
        if sky_dir.exists():
            for sky_file in sky_dir.glob("*.sky"):
                sky_file.unlink()
                files_removed.append(f"sky/{sky_file.name}")

        # Delete octree files
        if octree_dir.exists():
            for oct_file in octree_dir.glob("*.oct"):
                oct_file.unlink()
                files_removed.append(f"octree/{oct_file.name}")

        # Delete image outputs (conditionally delete .amb based on quality/mode change)
        if image_dir.exists():
            for img_file in image_dir.iterdir():
                if img_file.is_file():
                    # Delete .amb files if quality/mode changed, otherwise retain them
                    if img_file.suffix == ".amb" and not delete_amb_files:
                        files_retained.append(f"image/{img_file.name}")
                    else:
                        img_file.unlink()
                        files_removed.append(f"image/{img_file.name}")

    # SCENARIO 2: Rendering mode or quality changed (without timestep change)
    # Delete everything in image/ directory (including .amb)
    elif rendering_mode_changed or rendering_quality_changed:
        if rendering_mode_changed:
            print("SCENARIO 2: Rendering mode changed (cpu ↔ gpu)")
        else:
            print("SCENARIO 2: Rendering quality changed")
        print("-" * 80)
        print("Action: Delete ALL files in image/ directory")
        print("Reason: CPU/GPU or quality changes affect ambient calculations")
        print("        Best to regenerate for consistency\n")

        # Delete all image files including .amb
        if image_dir.exists():
            for img_file in image_dir.iterdir():
                if img_file.is_file():
                    img_file.unlink()
                    files_removed.append(f"image/{img_file.name}")

        # Retain octrees
        if octree_dir.exists():
            for oct_file in octree_dir.glob("*.oct"):
                files_retained.append(f"octree/{oct_file.name}")

    # SCENARIO 3: Resolution changed (without timestep change)
    # Delete .hdr and .tiff, conditionally delete .amb based on quality/mode
    elif resolution_changed:
        print("SCENARIO 3: Resolution changed")
        print("-" * 80)
        if delete_amb_files:
            print("Action: Delete .hdr, .tiff, and .amb files")
            print("Reason: Resolution + quality/mode change requires regeneration\n")
        else:
            print("Action: Delete .hdr and .tiff files, RETAIN .amb files")
            print("Reason: Ambient files are always 64x64 (resolution-independent)")
            print("        Only final renders need regeneration\n")

        # Delete rendered outputs and conditionally .amb files
        if image_dir.exists():
            for img_file in image_dir.iterdir():
                if img_file.is_file():
                    # Always delete .hdr and .tiff
                    if img_file.suffix in [".hdr", ".tiff", ".tif"]:
                        img_file.unlink()
                        files_removed.append(f"image/{img_file.name}")
                    # Delete .amb if quality/mode changed, otherwise retain
                    elif img_file.suffix == ".amb":
                        if delete_amb_files:
                            img_file.unlink()
                            files_removed.append(f"image/{img_file.name}")
                        else:
                            files_retained.append(f"image/{img_file.name}")

        # Retain octrees
        if octree_dir.exists():
            for oct_file in octree_dir.glob("*.oct"):
                files_retained.append(f"octree/{oct_file.name}")

    # Summary
    print("="*80)
    print("CLEANUP SUMMARY")
    print("="*80)
    print(f"Files removed:  {len(files_removed)}")
    print(f"Files retained: {len(files_retained)}")

    if files_removed:
        print(f"\nFirst 5 removed files:")
        for f in files_removed[:5]:
            print(f"  ✗ {f}")
        if len(files_removed) > 5:
            print(f"  ... and {len(files_removed) - 5} more")

    if files_retained:
        print(f"\nFirst 5 retained files:")
        for f in files_retained[:5]:
            print(f"  ✓ {f}")
        if len(files_retained) > 5:
            print(f"  ... and {len(files_retained) - 5} more")

    print("="*80 + "\n")


if __name__ == "__main__":
    # ========================================================================
    # SMART CLEANUP - Set TRUE for parameters that changed
    # ========================================================================
    # Use this for targeted cleanup based on what changed in your workflow

    smart_cleanup(
        timestep_changed=False,           # Set TRUE if timestep changed (e.g., 10min → 5min)
        resolution_changed=False,         # Set TRUE if image_resolution changed (e.g., 512 → 1024)
        rendering_mode_changed=False,     # Set TRUE if switched cpu ↔ gpu
        rendering_quality_changed=False   # Set TRUE if quality preset changed (e.g., 'draft' → 'stand')
    )

    # ========================================================================
    # LEGACY CLEANUP - Delete everything or keep specific files
    # ========================================================================
    # Uncomment below to use old-style cleanup (less intelligent)

    # retain_for_rerun = False
    # clear_outputs_folder(
    #     retain_amb_files=retain_for_rerun,
    #     retain_octree=retain_for_rerun
    # )
