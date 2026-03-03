"""
Archilume: Interactive Room Boundary Editor for HDR/TIFF Floor Plan Images

See archilume/hdr_aoi_editor.py for full documentation.
NOTE: daylight_workflow_iesve.py must be run before use of this editor.
"""

from archilume.hdr_aoi_editor import HdrAoiEditor

if __name__ == "__main__":
    editor = HdrAoiEditor()
    editor.launch()

    # --- DXF Background Layer [PRIORITY] ---
    # TODO: On editor launch, convert all .dxf files found in inputs_dir to PNG using ezdxf.
    #        Match each PNG to its corresponding floor plate by plan key (e.g. plan_ff_14000).
    #        Add a toggle (checkbox or button) to show/hide the DXF background beneath the HDR/TIFF layers.
    #        The DXF PNG should sit as the bottom canvas layer; HDR and TIFF renders are composited on top.

    # --- Drawing & Sub-room Editing ---
    # TODO: Improve sub-room polygon placement: prevent duplicate points, add edge/vertex snapping to parent room boundary.
    # TODO: Disable draw button unless a room is selected; make this requirement visually clear in the UI.
    # TODO: Auto-close unclosed polygons on Save or Backspace — link last point to first before labelling.
    #        Depends on: snapping/constraint to parent AOI boundary (above).
    # TODO: Handle input conflicts during draw mode — scroll, pan, and right-click events should be suppressed or
    #        explicitly handled to prevent accidental duplicate vertex placement or mode exit mid-polygon.

    # --- Room Divisions & Results Display ---
    # TODO: Fix Ctrl+Z undo after room division save — requires a persistent undo stack that tracks JSON state
    #        snapshots, not just in-memory canvas operations. Each save should push a state to the stack;
    #        Ctrl+Z should restore the previous snapshot and re-render.
    # TODO: Update result label positions after room division using a two-pass approach:
    #        (1) Identify the boundary edge with the highest mean DF value — this is the primary facade/window edge.
    #        (2) Place the label offset inward from that edge using pole-of-inaccessibility as a fallback if the
    #        DF-edge offset lands outside the polygon (e.g. for concave rooms).
    # TODO: Enforce 2-tier AOI hierarchy only — sub-rooms cannot themselves be parent rooms.

    # --- UI / UX ---
    # TODO: Add "Room Boundary" label above the save button group to clarify button scope.
    # TODO: Remove side border gaps in the UI to maximise the image viewport.
    # TODO: Mirror all hotkeys as labelled UI buttons (show key in brackets, e.g. "Divide [D]").
    #        Grey out context-sensitive buttons (e.g. Divider) when outside edit mode; add tooltips.

    # --- Copy Boundaries Across Levels ---
    # TODO: Add "Copy boundaries up" action: copy selected room(s) or entire floor AOIs to the level above.
    #        Retain original AOI names; only assign new names for new sub-boundaries.
    #        Must be undoable; support room-by-room or whole-floor copy.

    # --- Compliance Overlays ---
    # TODO: Display building-level and floor-plate BESS daylight factor pass/fail summary in a fixed UI panel
    #        (e.g. top or bottom bar), not overlaid on the canvas — avoids fragile dynamic placement logic.
    # TODO: Add pass/fail toggle overlay (green dot / red dot) with export of the marked-up image.
    # TODO: Integrate CNT and DF false-colour post-processing into the viewer: write outputs to a dedicated
    #        temp directory on open, delete on clean close. On launch, purge any stale temp files from prior
    #        sessions to prevent accumulation if the editor previously crashed.

    # --- Room Boundary Management ---
    # TODO: Allow deletion of a room boundary in the UI: remove from JSON, restore from source AOI file on reopen.
    #        Add a "Restore from source AOI" button for individual rooms or a selected group.
    # TODO: Add wall-thickness inset option: pull compliant area inward by a user-specified distance.

    # --- Multi-Resolution AOI Reuse ---
    # TODO: Allow pre-existing AOI boundaries to be reused across images rendered at different resolutions.
    #        AOI vertices are currently stored in pixel coordinates tied to a specific render resolution, so
    #        loading them against a different-resolution image causes misalignment.
    #        Approach: store vertices in normalised [0,1] image-space coordinates (or world coordinates) and
    #        convert to pixel space on load based on the actual image dimensions.
    #        NOTE: The pixel-to-world coordinate map (currently a single file) must also be generated per
    #        resolution, as the mapping changes with image size. Consider naming map files with a resolution
    #        suffix (e.g. _r2048.map) so the editor can select the correct map for the active image.
    #
    #        LONGER TERM — free the editor from the pixel-to-world map file entirely:
    #        The pixel↔world transform should be derived directly from the .hdr file itself.
    #        The .hdr header contains the view parameters (VIEW= line: type, vp, vd, vu, vh, vv) which
    #        define the world-space view frustum. However, the header does NOT contain the full rendered
    #        resolution — only the exposure/format metadata. The actual pixel dimensions must be queried
    #        separately (e.g. via `getinfo -d` or by reading the scanline count from the binary data).
    #        Once both are known, the pixel↔world mapping can be computed on-the-fly per .hdr file,
    #        removing the dependency on any external map file and making the editor fully self-contained.

    # --- Permutation Grid ---
    # TODO: Add 5×5 permutation grid for: quality, ceiling/wall/floor LRV, glass VLT, window frame LRV, resolution.
    #        For a selected failing room, highlight each permutation cell green/yellow/red based on DF% pass status.

    # --- Room Grouping ---
    # TODO: Allow multi-select grouping of rooms (click rooms then press "Group") to evaluate worst-case apartments.
    #        Support viewing group aggregate results or individual room results within the group.
    # TODO: Add level-based auto-grouping: group all rooms by floor level and export a separate AOI file per floor.
    #        Primary use case is large or courtyard-shaped buildings where a single view is illegible.
    #        Output AOI files should be named consistently so they can be directly used as workflow inputs without
    #        manual renaming. Include a UI confirmation step showing which floors will be exported before writing.

    # --- Workflow Integration ---
    # TODO: Add simulation and post-processing controls to the UI so users can run the full daylight IESVE workflow
    #        without touching the backend scripts. Scope first to local execution only — define clear UI states for
    #        idle, running, and complete with progress feedback. Defer Google Cloud execution to a later phase once
    #        local workflow is stable and the UI interaction model is proven.