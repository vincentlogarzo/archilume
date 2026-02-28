"""
Strip unwanted elements from an IFC file.

See archilume/ifc_strip.py for full documentation.
Usage: python strip_ifc.py [input.ifc [output.ifc]]
       If no arguments are given, a file picker window opens.
"""

from archilume.ifc_strip import IfcStrip
from archilume import config

if __name__ == "__main__":
    import sys
    from pathlib import Path

    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])
        output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    else:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        selected = filedialog.askopenfilename(
            title="Select IFC file to strip",
            initialdir=config.INPUTS_DIR,
            filetypes=[("IFC files", "*.ifc"), ("All files", "*.*")],
        )
        if not selected:
            print("No file selected.")
            sys.exit(0)
        input_path = Path(selected)
        output_path = None  # IfcStrip will default to _stripped suffix

    stripper = IfcStrip(input_path=input_path, output_path=output_path)
    stripper.load()
    stripper.show_class_tree(run_fn=stripper.run)  # strip runs in background while tree is open


# TODO: determine if output file can be written iteratively, it currently holds it all in memory untill complete and then writes the file at the end.

    # In IFC, doors create holes in walls through IfcOpeningElement entities. The relationship chain is:
    # IfcWall → IfcRelVoidsElement → IfcOpeningElement → IfcRelFillsElement → IfcDoor
    # If you remove only the IfcDoor, the IfcOpeningElement still exists — the wall still has a void/hole, just with nothing filling it. The wall geometry remains voided.

    # If you remove both IfcDoor and IfcOpeningElement (which is the current default — IfcOpeningElement is in DEFAULT_CLASSES_TO_REMOVE), then the IfcRelVoidsElement relationship is orphaned or removed too, and the wall's original solid geometry is restored — no hole.

    # So with your current defaults: walls become solid when doors are removed, because IfcOpeningElement is also stripped. If you were to add IfcDoor to the remove list but keep IfcOpeningElement off it, you'd get empty holes.

    # Please make this change, i would like door to be removed, and its ifcopening element remove instead of it currently being decimated which is taking ages.
