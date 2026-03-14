"""Launch the HDR/TIFF Room Boundary Editor.
Alternatively run 
```
uv run archilume
```
"""

from archilume.apps.hdr_aoi_editor_matplotlib import launch

if __name__ == "__main__":
    launch(debug=False)
