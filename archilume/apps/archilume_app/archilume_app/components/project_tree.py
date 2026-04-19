"""Room Browser panel — flat virtualised tree via tree_nodes computed var."""

import reflex as rx

from ..state import EditorState
from ..styles import COLORS, FONT_MONO, PANEL_CARD_TITLE, PROJECT_TREE_WIDTH
from .left_panel_sections import floor_plan_section, visualisation_section

_ROW_H = "26px"
_FONT = {"font_family": FONT_MONO, "font_size": "11px"}


def _hdr_row(node: dict) -> rx.Component:
    return rx.flex(
        rx.icon(
            tag=rx.cond(node["collapsed"], "chevron-right", "chevron-down"),
            size=12,
            style={"flex_shrink": "0", "color": COLORS["text_dim"], "cursor": "pointer"},
            on_click=EditorState.toggle_hdr_collapse(node["hdr_name"]),
        ),
        rx.icon(
            tag="image",
            size=13,
            style={"flex_shrink": "0",
                   "color": rx.cond(node["is_current_hdr"], COLORS["accent"], COLORS["text_sec"])},
        ),
        rx.text(
            node["label"],
            style={**_FONT,
                   "overflow": "hidden", "text_overflow": "ellipsis",
                   "white_space": "nowrap", "flex": "1",
                   "font_weight": rx.cond(node["is_current_hdr"], "600", "400"),
                   "cursor": "pointer"},
            color=rx.cond(node["is_current_hdr"], COLORS["accent"], COLORS["text_pri"]),
            on_click=EditorState.navigate_to_hdr(node["hdr_idx"]),
        ),
        align="center",
        gap="5px",
        style={
            "height": _ROW_H,
            "padding": "0 8px",
            "flex_shrink": "0",
        },
        background=rx.cond(node["is_current_hdr"], COLORS["hover"], "transparent"),
        _hover={"background": COLORS["hover"]},
    )



_LINE_COLOR = COLORS["text_dim"]
_LINE_OPACITY = "0.4"
# Horizontal midpoint within the connector column where the vertical line sits
_VX = "6px"
# Width of the connector column for parent rows; children add a second column
_COL_W = "16px"

# --- Child room connector: dotted rail + rounded node ---
_CHILD_DOT_SIZE = "5px"
_CHILD_RAIL_COLOR = COLORS["accent"]
_CHILD_RAIL_OPACITY = "0.22"
_CHILD_DOT_OPACITY = "0.50"


def _connector(node: dict) -> rx.Component:
    """
    Tree connector with two styles:
    - parent_room: classic solid 1px lines (unchanged)
    - child_room: refined dotted vertical rail with a small circular node
      at the branch point, giving child rows a distinctive visual identity.
    """
    line_style_base = {
        "position": "absolute",
        "background": _LINE_COLOR,
        "opacity": _LINE_OPACITY,
    }

    # --- Parent-room connector (unchanged classic style) ---
    own_vert_h = rx.cond(node["connector"] == "T", "100%", "50%")

    col_b_parent = rx.box(
        rx.box(style={**line_style_base,
                      "left": _VX, "top": "0",
                      "width": "1px", "height": own_vert_h}),
        rx.box(style={**line_style_base,
                      "left": _VX, "top": "50%",
                      "width": _VX, "height": "1px"}),
        style={"position": "relative", "width": _COL_W,
               "flex_shrink": "0", "align_self": "stretch"},
    )

    # --- Child-room connector: dotted rail + dot node ---
    child_rail_style = {
        "position": "absolute",
        "border_left": f"1px dashed {_CHILD_RAIL_COLOR}",
        "opacity": _CHILD_RAIL_OPACITY,
    }

    child_vert_h = rx.cond(node["connector"] == "T", "100%", "50%")

    col_b_child = rx.box(
        # dashed vertical rail
        rx.box(style={**child_rail_style,
                      "left": _VX, "top": "0",
                      "width": "0", "height": child_vert_h}),
        # horizontal dashed branch
        rx.box(style={**child_rail_style,
                      "left": _VX, "top": "50%",
                      "width": _VX, "height": "0",
                      "border_left": "none",
                      "border_top": f"1px dashed {_CHILD_RAIL_COLOR}"}),
        # circular node at branch point
        rx.box(style={
            "position": "absolute",
            "left": f"calc({_VX} - 2.5px)", "top": f"calc(50% - 2.5px)",
            "width": _CHILD_DOT_SIZE, "height": _CHILD_DOT_SIZE,
            "border_radius": "50%",
            "background": _CHILD_RAIL_COLOR,
            "opacity": _CHILD_DOT_OPACITY,
        }),
        style={"position": "relative", "width": _COL_W,
               "flex_shrink": "0", "align_self": "stretch"},
    )

    # col-A: parent continuation line (child rows only)
    col_a_classic = rx.box(
        rx.box(style={**line_style_base,
                      "left": _VX, "top": "0",
                      "width": "1px", "height": "100%",
                      "display": rx.cond(node["parent_continues"] == "1", "block", "none")}),
        style={"position": "relative", "width": _COL_W,
               "flex_shrink": "0", "align_self": "stretch"},
    )
    col_a_child = rx.box(
        rx.box(style={
            "position": "absolute",
            "left": _VX, "top": "0",
            "width": "0", "height": "100%",
            "border_left": f"1px dashed {_CHILD_RAIL_COLOR}",
            "opacity": _CHILD_RAIL_OPACITY,
            "display": rx.cond(node["parent_continues"] == "1", "block", "none"),
        }),
        style={"position": "relative", "width": _COL_W,
               "flex_shrink": "0", "align_self": "stretch"},
    )

    return rx.cond(
        node["node_type"] == "child_room",
        rx.flex(
            col_a_child,
            col_b_child,
            style={"flex_shrink": "0", "align_self": "stretch"},
        ),
        # parent_room — classic single col_b only
        col_b_parent,
    )


def _room_row(node: dict) -> rx.Component:
    connector = _connector(node)
    # Offset spacer so the parent-room connector line centres on the HDR row's
    # image icon.  HDR icon centre ≈ 8px padding + 12px chevron + 5px gap + 6.5px
    # = ~31.5px.  col-B line sits at 6px into the 16px column, so we need
    # ~25.5px of left padding → add an 18px spacer before the connector (row
    # already has 8px left padding, giving 8+18+6 = 32px ≈ icon centre).
    # Child rows have col-A (16px) before col-B, so no extra spacer needed there.
    spacer = rx.box(style={"width": "18px", "flex_shrink": "0"})
    # For parent rooms with children, draw a vertical trunk line from the row
    # midpoint downward at the x-position where children's col-B vertical sits.
    # Position: 8px(pad) + 18px(spacer) + 5px(gap) + 16px(col-A) + 6px(_VX) = 53px.
    child_trunk = rx.cond(
        (node["node_type"] == "parent_room") & (node["has_children"]),
        rx.box(style={
            "position": "absolute",
            "left": "53px", "top": "50%",
            "width": "0", "height": "50%",
            "border_left": f"1px dashed {_CHILD_RAIL_COLOR}",
            "opacity": _CHILD_RAIL_OPACITY,
        }),
        rx.fragment(),
    )
    # --- Child room rows get a refined accent treatment ---
    is_child = node["node_type"] == "child_room"

    # Left accent bar for child rooms (visible on selected/hover via CSS)
    child_accent_bar = rx.cond(
        is_child,
        rx.box(style={
            "position": "absolute",
            "left": "0", "top": "3px", "bottom": "3px",
            "width": "2px",
            "border_radius": "1px",
            "background": COLORS["accent"],
            "opacity": rx.cond(node["selected"], "1", "0"),
            "transition": "opacity 0.15s ease",
        }),
        rx.fragment(),
    )

    # Text color: child rooms use slightly softer default, brightens on select
    child_text_color = rx.cond(
        node["selected"],
        COLORS["accent"],
        rx.cond(is_child, COLORS["text_sec"], COLORS["text_pri"]),
    )

    # Font size: child rooms slightly smaller for visual hierarchy
    child_font_size = rx.cond(is_child, "10.5px", "11px")

    return rx.flex(
        child_trunk,
        child_accent_bar,
        spacer,
        connector,
        rx.text(
            node["label"],
            style={**_FONT,
                   "overflow": "hidden", "text_overflow": "ellipsis",
                   "white_space": "nowrap", "flex": "1",
                   "font_size": child_font_size,
                   "letter_spacing": rx.cond(is_child, "0.01em", "0"),
                   "transition": "color 0.12s ease"},
            color=child_text_color,
        ),
        rx.cond(
            node["room_type"] != "",
            rx.badge(
                node["room_type"],
                style={"font_family": FONT_MONO, "font_size": "9px",
                       "padding": "0 4px", "flex_shrink": "0", "cursor": "pointer"},
                color=rx.cond(node["room_type"] == "NONE", COLORS["text_sec"], COLORS["accent2"]),
                background=COLORS["deep"],
                border="1px solid", border_color=COLORS["panel_bdr"],
                _hover={"background": COLORS["hover"], "border_color": rx.cond(node["room_type"] == "NONE", COLORS["text_sec"], COLORS["accent2"])},
                on_click=EditorState.cycle_room_type(node["room_idx"]).stop_propagation,
            ),
            rx.fragment(),
        ),
        align="center",
        gap="5px",
        style={
            "height": _ROW_H,
            "padding": "0 8px 0 8px",
            "cursor": "pointer",
            "flex_shrink": "0",
            "position": "relative",
            "transition": "background 0.12s ease",
        },
        background=rx.cond(node["selected"], COLORS["btn_on"], "transparent"),
        _hover={"background": COLORS["hover"]},
        on_click=lambda e: EditorState.select_room_or_multi(node["room_idx"], e),
    )


def _render_tree_node(node: dict) -> rx.Component:
    return rx.cond(
        node["node_type"] == "hdr",
        _hdr_row(node),
        _room_row(node),
    )


def _tree_header() -> rx.Component:
    return rx.flex(
        rx.flex(
            rx.icon(
                tag=rx.cond(EditorState.room_browser_section_open, "chevron-down", "chevron-right"),
                size=12,
                style={"color": COLORS["text_pri"], "flex_shrink": "0"},
            ),
            rx.text(
                "Room Browser",
                style={
                    **PANEL_CARD_TITLE,
                    "padding": "0",
                    "margin_left": "4px",
                    "font_weight": "700",
                    "overflow": "hidden",
                    "text_overflow": "ellipsis",
                    "white_space": "nowrap",
                },
                color=COLORS["text_pri"],
            ),
            on_click=EditorState.toggle_room_browser_section,
            align="center",
            style={"cursor": "pointer", "flex_shrink": "1", "min_width": "0"},
        ),
        rx.spacer(),
        rx.tooltip(
            rx.icon_button(
                rx.icon(tag="layers", size=12),
                variant="ghost", size="1",
                on_click=EditorState.toggle_image_variant.stop_propagation,
                style={"color": COLORS["text_dim"], "flex_shrink": "0"},
            ),
            content="Toggle Image Layers [T]", side="bottom",
        ),
        rx.box(style={"width": "1px", "height": "16px", "background": COLORS["panel_bdr"], "flex_shrink": "0"}),
        rx.tooltip(
            rx.button(
                rx.cond(EditorState.all_rooms_selected, "Unselect All", "Select All"),
                variant="ghost", size="1",
                on_click=EditorState.select_all_rooms.stop_propagation,
                style={**_FONT, "font_size": "9px", "white_space": "nowrap",
                       "color": COLORS["text_dim"], "padding": "0 4px", "flex_shrink": "0"},
            ),
            content="Ctrl+A", side="bottom",
        ),
        rx.box(style={"width": "1px", "height": "16px", "background": COLORS["panel_bdr"], "flex_shrink": "0"}),
        rx.tooltip(
            rx.icon_button(
                rx.icon(tag="chevrons-down-up", size=12),
                variant="ghost", size="1",
                on_click=EditorState.collapse_all_hdrs.stop_propagation,
                style={"color": COLORS["text_dim"], "flex_shrink": "0"},
            ),
            content="Collapse All", side="bottom",
        ),
        rx.tooltip(
            rx.icon_button(
                rx.icon(tag="chevrons-up-down", size=12),
                variant="ghost", size="1",
                on_click=EditorState.expand_all_hdrs.stop_propagation,
                style={"color": COLORS["text_dim"], "flex_shrink": "0"},
            ),
            content="Expand All", side="bottom",
        ),
        align="center",
        style={
            "padding": "0 6px 0 8px",
            "flex_shrink": "0",
            "gap": "6px",
            "height": "36px",
            "background": COLORS["deep"],
            "border_top": "1px solid",
            "border_bottom": "1px solid",
            "border_color": COLORS["panel_bdr"],
            "_hover": {"background": COLORS["hover"]},
        },
    )



_RESIZE_SCRIPT = rx.script("""
(function() {
    let dragging = false, startX = 0, startW = 0, activePanel = null;
    window.addEventListener('mousemove', function(e) {
        if (!dragging || !activePanel) return;
        const newW = Math.min(600, Math.max(160, startW + (e.clientX - startX)));
        activePanel.style.width = newW + 'px';
        var vc = document.getElementById('viewport-container');
        if (vc && window._recomputeOverlayTransform) {
            var w = vc.clientWidth, h = vc.clientHeight;
            if (w > 0 && h > 0) window._recomputeOverlayTransform(w, h);
        }
    });
    window.addEventListener('mouseup', function() {
        if (!dragging) return;
        dragging = false; activePanel = null;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        var vc = document.getElementById('viewport-container');
        if (vc && vc.clientWidth > 0 && window.applyEvent) {
            try {
                window.applyEvent('editor_state.set_viewport_size', {
                    data: { w: Math.round(vc.clientWidth), h: Math.round(vc.clientHeight) }
                });
            } catch (e) {}
        }
    });
    function attachHandle(handle, panel) {
        handle.addEventListener('mousedown', function(e) {
            dragging = true; startX = e.clientX;
            startW = panel.getBoundingClientRect().width;
            activePanel = panel;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            e.preventDefault();
        });
    }
    function tryAttach() {
        const handle = document.getElementById('project-tree-resize-handle');
        const panel  = document.getElementById('project-tree-panel');
        if (handle && panel) attachHandle(handle, panel);
    }
    const observer = new MutationObserver(tryAttach);
    observer.observe(document.body, { childList: true, subtree: true });
    tryAttach();
})();
""")


def project_tree() -> rx.Component:
    return rx.cond(
        EditorState.project_tree_open,
        rx.box(
            _tree_header(),
            # Tree list sits directly below the header at its natural height so
            # the floor-plan section hugs the bottom of the list when the list
            # is short. `flex: 0 1 auto` + `min_height: 0` lets the list shrink
            # and scroll internally when the list grows taller than the panel.
            rx.cond(
                EditorState.room_browser_section_open,
                rx.box(
                    rx.foreach(EditorState.tree_nodes, _render_tree_node),
                    style={
                        "overflow_y": "auto",
                        "flex": "0 1 auto",
                        "min_height": "0",
                        "scrollbar_width": "thin",
                        "scrollbar_color": f"{COLORS['panel_bdr']} transparent",
                    },
                ),
                rx.fragment(),
            ),
            # Floor plan section: fixed size, never shrinks.
            rx.box(floor_plan_section(), style={"flex_shrink": "0"}),
            # Visualisation (falsecolour + contour) settings.
            rx.box(visualisation_section(), style={"flex_shrink": "0"}),
            # Absorb any leftover vertical space so the list+floor-plan stack
            # stays top-packed when content is short.
            rx.box(style={"flex": "1 1 auto"}),
            rx.box(
                id="project-tree-resize-handle",
                style={
                    "position": "absolute", "top": "0", "right": "0",
                    "width": "4px", "height": "100%",
                    "cursor": "col-resize", "z_index": "10",
                    "_hover": {"background": COLORS["accent"]},
                },
            ),
            _RESIZE_SCRIPT,
            id="project-tree-panel",
            style={
                "width": PROJECT_TREE_WIDTH, "min_width": "160px", "max_width": "600px",
                "position": "relative", "display": "flex", "flex_direction": "column",
                "overflow": "hidden",
            },
            background=COLORS["panel_bg"],
            border_right="1px solid", border_color=COLORS["panel_bdr"],
        ),
        rx.fragment(),
    )
