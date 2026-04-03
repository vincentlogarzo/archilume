"""Room Browser panel — flat virtualised tree via tree_nodes computed var."""

import reflex as rx

from ..state import EditorState
from ..styles import COLORS, FONT_MONO, PROJECT_TREE_WIDTH

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


def _room_row(node: dict) -> rx.Component:
    return rx.flex(
        # indent spacer
        rx.box(style={"width": node["indent"], "flex_shrink": "0"}),
        rx.icon(
            tag="chevron-right",
            size=11,
            style={"flex_shrink": "0",
                   "color": rx.cond(node["selected"], COLORS["accent"], COLORS["text_dim"])},
        ),
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
                       "padding": "0 4px", "flex_shrink": "0"},
                color=COLORS["accent2"],
                background=COLORS["deep"],
                border="1px solid", border_color=COLORS["panel_bdr"],
            ),
            rx.fragment(),
        ),
        align="center",
        gap="5px",
        style={
            "height": _ROW_H,
            "padding": "0 8px",
            "cursor": "pointer",
            "flex_shrink": "0",
        },
        background=rx.cond(node["selected"], COLORS["btn_on"], "transparent"),
        _hover={"background": COLORS["hover"]},
        on_click=EditorState.select_room(node["room_idx"]),
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
        rx.button(
            rx.cond(EditorState.all_rooms_selected, "Unselect All", "Select All"),
            variant="ghost", size="1",
            on_click=EditorState.select_all_rooms,
            style={**_FONT, "font_size": "9px", "white_space": "nowrap",
                   "color": COLORS["text_dim"], "padding": "0 3px", "flex_shrink": "0"},
        ),
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
        style={"padding": "0 4px", "flex_shrink": "0", "gap": "4px",
               "height": "36px", "overflow": "hidden"},
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
