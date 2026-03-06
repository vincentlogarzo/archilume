"""
Archilume: Interactive Room Boundary Editor for HDR/TIFF Floor Plan Images

See archilume/hdr_aoi_editor.py for full documentation.
"""

from archilume.apps.hdr_aoi_editor_matplotlib import HdrAoiEditor

if __name__ == "__main__":
    editor = HdrAoiEditor(
        #optional: auto-load PDF overlay
        project     = "527DM",  # Optional: sub-folder within inputs/
        pdf_path    = "plans/SK01.09-PLAN - TYPICAL(P1).pdf",
    )
    editor.launch()
