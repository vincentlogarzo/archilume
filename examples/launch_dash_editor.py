"""Launch the Dash HDR AOI Editor with hot-reload enabled.

The browser opens automatically at http://127.0.0.1:8050/
Edits to dash_editor.py are picked up live without relaunching.

Optionally set a project name to pre-load project context.
"""

from archilume.apps.dash_editor import launch

if __name__ == "__main__":
    launch(
        project ="527DP-gcloud-lowRes-GregW", 
        debug   =True
        )
