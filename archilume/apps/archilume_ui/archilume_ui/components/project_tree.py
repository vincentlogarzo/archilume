"""Room Browser panel — flat virtualised tree via tree_nodes computed var."""

import reflex as rx

from ..state import EditorState
from ..styles import COLORS, FONT_MONO, PROJECT_TREE_WIDTH
from .left_panel_sections import floor_plan_section

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


def _connector(node: dict) -> rx.Component:
    """
    Classic tree connector rendered from the node's precomputed `connector`
    ("T" or "L") and `parent_continues` fields.

    Layout (two-column for child_room, one-column for parent_room):

      col-A (16px): parent's vertical continuation line (child_room only, when parent_continues)
      col-B (16px): own vertical + horizontal branch

    For "T": vertical runs full height (continues to next sibling).
    For "L": vertical runs top-half only (last sibling, line stops here).
    """
    line_style_base = {
        "position": "absolute",
        "background": _LINE_COLOR,
        "opacity": _LINE_OPACITY,
    }

    # col-B: own connector — vertical segment from top.
    # "T" = more siblings → full height.
    # "L" = last sibling → top-half only.
    own_vert_h = rx.cond(node["connector"] == "T", "100%", "50%")

    col_b = rx.box(
        # vertical segment
        rx.box(style={**line_style_base,
                      "left": _VX, "top": "0",
                      "width": "1px", "height": own_vert_h}),
        # horizontal branch to label (always at row midpoint)
        rx.box(style={**line_style_base,
                      "left": _VX, "top": "50%",
                      "width": _VX, "height": "1px"}),
        style={"position": "relative", "width": _COL_W,
               "flex_shrink": "0", "align_self": "stretch"},
    )

    # col-A: parent continuation — always rendered for child rows, but line is
    # hidden via display:none when parent_continues is False.
    col_a = rx.box(
        rx.box(style={**line_style_base,
                      "left": _VX, "top": "0",
                      "width": "1px", "height": "100%",
                      "display": rx.cond(node["parent_continues"] == "1", "block", "none")}),
        style={"position": "relative", "width": _COL_W,
               "flex_shrink": "0", "align_self": "stretch"},
    )

    return rx.cond(
        node["node_type"] == "child_room",
        rx.flex(
            col_a,
            col_b,
            style={"flex_shrink": "0", "align_self": "stretch"},
        ),
        # parent_room — single col_b only
        col_b,
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
            "width": "1px", "height": "50%",
            "background": _LINE_COLOR,
            "opacity": _LINE_OPACITY,
        }),
        rx.fragment(),
    )
    return rx.flex(
        child_trunk,
        spacer,
        connector,
        rx.text(
            node["label"],
            style={**_FONT,
                   "overflow": "hidden", "text_overflow": "ellipsis",
                   "white_space": "nowrap", "flex": "1"},
            color=rx.cond(node["selected"], COLORS["accent"], COLORS["text_pri"]),
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
        rx.text(
            "Room Browser",
            style={**_FONT, "font_size": "11px", "text_transform": "uppercase",
                   "letter_spacing": "0.08em", "overflow": "hidden",
                   "text_overflow": "ellipsis", "white_space": "nowrap"},
            color=COLORS["text_dim"],
        ),
        rx.spacer(),
        rx.tooltip(
            rx.icon_button(
                rx.icon(tag="layers", size=12),
                variant="ghost", size="1",
                on_click=EditorState.toggle_image_variant,
                style={"color": COLORS["text_dim"], "flex_shrink": "0"},
            ),
            content="Toggle Image Layers [T]", side="bottom",
        ),
        rx.box(style={"width": "1px", "height": "16px", "background": COLORS["panel_bdr"], "flex_shrink": "0"}),
        rx.tooltip(
            rx.button(
                rx.cond(EditorState.all_rooms_selected, "Unselect All", "Select All"),
                variant="ghost", size="1",
                on_click=EditorState.select_all_rooms,
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
                on_click=EditorState.collapse_all_hdrs,
                style={"color": COLORS["text_dim"], "flex_shrink": "0"},
            ),
            content="Collapse All", side="bottom",
        ),
        rx.tooltip(
            rx.icon_button(
                rx.icon(tag="chevrons-up-down", size=12),
                variant="ghost", size="1",
                on_click=EditorState.expand_all_hdrs,
                style={"color": COLORS["text_dim"], "flex_shrink": "0"},
            ),
            content="Expand All", side="bottom",
        ),
        align="center",
        style={"padding": "0 6px", "flex_shrink": "0", "gap": "6px",
               "height": "36px"},
        border_bottom="1px solid", border_color=COLORS["panel_bdr"],
    )



_RESIZE_SCRIPT = rx.script("""
(function() {
    let dragging = false, startX = 0, startW = 0, activePanel = null;
    window.addEventListener('mousemove', function(e) {
        if (!dragging || !activePanel) return;
        const newW = Math.min(600, Math.max(160, startW + (e.clientX - startX)));
        activePanel.style.width = newW + 'px';
    });
    window.addEventListener('mouseup', function() {
        if (!dragging) return;
        dragging = false; activePanel = null;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
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
            rx.box(
                rx.foreach(EditorState.tree_nodes, _render_tree_node),
                style={
                    "overflow_y": "auto",
                    "flex": "1",
                    "scrollbar_width": "thin",
                    "scrollbar_color": f"{COLORS['panel_bdr']} transparent",
                },
            ),
            floor_plan_section(),
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
