
# archilume/archilume/apps/dash_app.py
#
# Bare-bones Dash UI — mirrors the full feature-set of hdr_aoi_editor_matplotlib.py.
# All buttons, panels, and tree structure from the matplotlib editor are reproduced here
# as static layout. Callbacks are stubs only.
#
# Run:  python -m archilume.apps.dash_app
#       http://127.0.0.1:8050/
#

import json
import os
import re
import shutil
import threading
import time
import webbrowser
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import ALL, ctx, html, dcc, no_update, Input, Output, State
from dash_iconify import DashIconify

from archilume.apps.dash_editor import EditorState, build_figure, render_tree
from archilume.apps.project_config import (
    list_projects,
    save_project_toml,
    set_last_project,
)

app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Syne:wght@400;600;700&display=swap"
    ],
    suppress_callback_exceptions=True,
)

# ── Server-side state ─────────────────────────────────────────────────────────

STATE: Optional[EditorState] = None


def _init_state(project: Optional[str] = None) -> None:
    global STATE
    STATE = EditorState(project=project)
    # Kick off DF computation in background for the initial HDR
    def _initial_df():
        if STATE is not None:
            STATE.load_df_image()
            STATE._compute_all_room_df_results()
    threading.Thread(target=_initial_df, daemon=True).start()

# ---------------------------------------------------------------- colour tokens --

C = {
    "sidebar":     "#f5f6f7",       # near-white sidebar
    "sidebar_act": "#e8eaed",       # active sidebar item bg
    "header":      "#ffffff",       # pure white header / panels
    "panel_bg":    "#ffffff",
    "panel_bdr":   "#e2e5e9",       # light slate border
    "viewport":    "#f0f2f4",       # very light grey canvas bg
    "dot":         "#c4cad1",       # dot-grid dots
    "text_pri":    "#1a1f27",       # near-black primary text
    "text_sec":    "#5a6472",       # medium slate secondary text
    "text_dim":    "#9ba6b2",       # muted tertiary text
    "accent":      "#0d9488",       # teal-600 accent
    "accent2":     "#4f6ef7",       # indigo accent
    "hover":       "#eef0f3",       # subtle hover
    "btn_on":      "#ccfbf1",       # teal tint for active toggles
    "btn_off":     "transparent",
    "danger":      "#dc2626",       # red-600
    "warning":     "#d97706",       # amber-600
    "success":     "#059669",       # emerald-600
    "deep":        "#f0f2f4",       # light bg for inset inputs
}

FONT_HEAD = "Syne, sans-serif"
FONT_MONO = "'DM Mono', monospace"

# ------------------------------------------------------------------- helpers --

def sb_btn(icon, btn_id, tip, active=False, danger=False):
    """Left-sidebar icon button with tooltip."""
    color = C["accent"] if active else (C["danger"] if danger else C["text_sec"])
    bg = C["sidebar_act"] if active else "transparent"
    return html.Div([
        dbc.Button(
            DashIconify(icon=icon, width=20, color=color),
            id=btn_id,
            color="link",
            style={
                "padding": "9px 0",
                "width": "48px",
                "display": "flex",
                "justifyContent": "center",
                "borderRadius": "6px",
                "backgroundColor": bg,
                "border": "none",
                "transition": "background 0.12s",
            },
        ),
        dbc.Tooltip(tip, target=btn_id, placement="right"),
    ], style={"width": "48px", "marginBottom": "3px"})


def divider_line():
    return html.Div(style={
        "height": "1px",
        "backgroundColor": C["panel_bdr"],
        "margin": "6px 8px",
        "opacity": "0.5",
    })


def panel_label(text):
    return html.Div(text, style={
        "fontSize": "9px",
        "fontFamily": FONT_MONO,
        "fontWeight": "500",
        "letterSpacing": "0.12em",
        "color": C["text_dim"],
        "textTransform": "uppercase",
        "padding": "8px 12px 3px",
        "userSelect": "none",
    })


def panel_card(title, children, style=None):
    base = {
        "backgroundColor": C["panel_bg"],
        "border": f"1px solid {C['panel_bdr']}",
        "borderRadius": "6px",
        "marginBottom": "8px",
    }
    if style:
        base.update(style)
    return html.Div([
        html.Div(title, style={
            "fontSize": "10px",
            "fontFamily": FONT_MONO,
            "color": C["text_sec"],
            "fontWeight": "500",
            "letterSpacing": "0.08em",
            "padding": "6px 10px 5px",
            "borderBottom": f"1px solid {C['panel_bdr']}",
            "textTransform": "uppercase",
        }),
        html.Div(children, style={"padding": "8px 10px"}),
    ], style=base)


def action_btn(label, btn_id, icon, color_bg=C["hover"], color_text=C["text_sec"], tip=None):
    b = dbc.Button([
        DashIconify(icon=icon, width=13, style={"marginRight": "5px"}),
        label,
    ], id=btn_id, color="secondary", size="sm",
       style={
           "width": "100%",
           "fontFamily": FONT_MONO,
           "fontSize": "11px",
           "marginBottom": "5px",
           "backgroundColor": color_bg,
           "color": color_text,
           "border": f"1px solid {C['panel_bdr']}",
           "textAlign": "left",
       })
    if tip:
        return html.Div([b, dbc.Tooltip(tip, target=btn_id)])
    return b


def room_type_btn(label, btn_id, active=False):
    bg = C["btn_on"] if active else C["deep"]
    border_color = C["accent"] if active else C["panel_bdr"]
    color = C["accent"] if active else C["text_sec"]
    return dbc.Button(label, id=btn_id, size="sm", color="secondary", style={
        "fontFamily": FONT_MONO,
        "fontSize": "10px",
        "padding": "3px 7px",
        "backgroundColor": bg,
        "border": f"1px solid {border_color}",
        "color": color,
        "marginRight": "3px",
        "marginBottom": "3px",
        "borderRadius": "3px",
    })


def kbd(key):
    return html.Span(key, style={
        "fontFamily": FONT_MONO,
        "fontSize": "9px",
        "color": C["text_dim"],
        "backgroundColor": C["deep"],
        "border": f"1px solid {C['panel_bdr']}",
        "borderRadius": "3px",
        "padding": "1px 4px",
        "marginLeft": "4px",
    })


# -------------------------------------------------------------- left sidebar --
#
# Mirrors _setup_left_sidebar() in the matplotlib editor.
# Buttons (top→bottom):
#   Menu toggle | Project | --- | Extract | Export |
#   --- | Floor Plan Toggle | Floor Plan Page | Resize Plan Mode |
#   --- | Image Layer Toggle | Reset Zoom |
#   --- | DF% Placement | Edit Mode | Ortho Lines |
#   --- (spacer) | Annotation Scale (slider) |
#   --- | History | Settings

left_sidebar = html.Div([
    # ---- Nav ----
    sb_btn("lucide:menu",          "sb-menu",          "Toggle Project Browser"),
    html.Div(style={"height": "4px"}),
    sb_btn("lucide:folder-open",   "sb-open-project",  "Open Project"),
    sb_btn("lucide:folder-plus",   "sb-create-project","Create New Project"),
    divider_line(),

    # ---- Archive ----
    sb_btn("lucide:archive-restore","sb-extract",      "Extract Archive"),
    sb_btn("lucide:file-bar-chart", "sb-export",       "Export & Archive"),
    divider_line(),

    # ---- Floor plan overlay ----
    sb_btn("lucide:layout-panel-top","sb-overlay-toggle", "Floor Plan: OFF  (click to toggle)"),
    sb_btn("lucide:refresh-cw",     "sb-overlay-page",  "Change Floor Plan Page"),
    sb_btn("lucide:maximize",       "sb-overlay-align", "Resize Plan Mode: OFF"),
    divider_line(),

    # ---- Image / View ----
    sb_btn("lucide:layers",         "sb-image-toggle",  "Toggle Image Layers  [T]"),
    sb_btn("lucide:zoom-in",        "sb-reset-zoom",    "Reset Zoom  [R]"),
    divider_line(),

    # ---- Drawing tools (toggle) ----
    sb_btn("lucide:crosshair",      "sb-placement",     "DF% Placement: OFF  [P]"),
    sb_btn("lucide:pen-line",       "sb-edit-mode",     "Boundary Edit Mode: OFF  [E]"),
    sb_btn("lucide:corner-down-right","sb-ortho",       "Ortho Lines: ON  [O]", active=True),
    divider_line(),

    # ---- Annotation scale slider ----
    html.Div([
        html.Div("Aa", style={
            "fontSize": "9px", "fontFamily": FONT_MONO,
            "color": C["text_dim"], "textAlign": "center", "marginBottom": "4px",
        }),
        dcc.Slider(
            id="slider-annotation-scale",
            min=0.5, max=2.0, step=0.05, value=1.0,
            vertical=True,
            verticalHeight=80,
            marks=None,
            tooltip={"placement": "right", "always_visible": False},
        ),
    ], style={
        "width": "48px", "display": "flex", "flexDirection": "column",
        "alignItems": "center", "padding": "4px 0 8px",
    }),
    divider_line(),

    # ---- Spacer ----
    html.Div(style={"flex": "1"}),

    # ---- Bottom ----
    sb_btn("lucide:clock-3",        "sb-history",       "History"),
    sb_btn("lucide:settings-2",     "sb-settings",      "Settings"),

], style={
    "width": "52px",
    "height": "100vh",
    "backgroundColor": C["sidebar"],
    "display": "flex",
    "flexDirection": "column",
    "alignItems": "center",
    "padding": "10px 0",
    "position": "fixed",
    "top": 0,
    "left": 0,
    "zIndex": 1000,
    "borderRight": f"1px solid {C['panel_bdr']}",
    "overflowY": "auto",
    "scrollbarWidth": "none",
})

# ----------------------------------------------------------- project tree ----
#
# Mirrors the right sidebar tree from the matplotlib editor:
#
#   ▼ [HDR filename]
#     ▶  Layer 1 – False Colour TIFF
#     ▶  Layer 2 – Contour TIFF
#     ▶  Layer 3 – PDF Floor Plan Overlay
#     ▼  Layer 4 – Room Boundaries
#         ▼ U101       BED     👁 ⚙
#             U101_BED1       👁 ⚙
#             U101_LIV1       👁 ⚙
#         ▼ U102       LIVING  👁 ⚙
#             U102_BED1       👁 ⚙

def _tree_row(label, icon, depth=0, expanded=None, highlight=False,
              badge=None, eye=True, cog=True, dimmed=False):
    """Single row in the project tree."""
    indent = depth * 14
    chevron = None
    if expanded is not None:
        chevron_icon = "lucide:chevron-down" if expanded else "lucide:chevron-right"
        chevron = DashIconify(icon=chevron_icon, width=11, color=C["text_dim"],
                              style={"marginRight": "3px", "flexShrink": "0"})
    else:
        chevron = html.Div(style={"width": "14px", "flexShrink": "0"})

    row_bg = C["hover"] if highlight else "transparent"
    label_color = C["accent"] if highlight else (C["text_dim"] if dimmed else C["text_pri"])
    icon_color = C["accent"] if highlight else (C["text_dim"] if dimmed else C["text_sec"])

    actions = []
    if eye:
        actions.append(DashIconify(icon="lucide:eye", width=12, color=C["text_dim"],
                                   style={"cursor": "pointer", "marginLeft": "5px"}))
    if cog:
        actions.append(DashIconify(icon="lucide:settings-2", width=12, color=C["text_dim"],
                                   style={"cursor": "pointer", "marginLeft": "4px"}))

    badge_el = []
    if badge:
        badge_el = [html.Span(badge, style={
            "fontSize": "9px", "fontFamily": FONT_MONO,
            "color": C["accent2"], "backgroundColor": "#eef4fe",
            "border": f"1px solid {C['panel_bdr']}",
            "borderRadius": "3px", "padding": "0 4px", "marginLeft": "5px",
            "flexShrink": "0",
        })]

    return html.Div([
        html.Div(style={"width": f"{indent}px", "flexShrink": "0"}),
        chevron,
        DashIconify(icon=icon, width=13, color=icon_color,
                    style={"marginRight": "5px", "flexShrink": "0"}),
        html.Span(label, style={
            "fontSize": "11px", "fontFamily": FONT_MONO,
            "color": label_color, "flexGrow": "1",
            "whiteSpace": "nowrap", "overflow": "hidden", "textOverflow": "ellipsis",
        }),
        *badge_el,
        *actions,
    ], style={
        "display": "flex", "alignItems": "center",
        "padding": "3px 8px",
        "borderRadius": "4px",
        "backgroundColor": row_bg,
        "cursor": "pointer",
        "marginBottom": "1px",
        "opacity": "0.45" if dimmed else "1",
    })


# Tree collapse/expand controls header
tree_controls = html.Div([
    html.Span("Project Browser", style={
        "fontSize": "10px", "fontFamily": FONT_MONO, "fontWeight": "500",
        "letterSpacing": "0.1em", "color": C["text_dim"],
        "textTransform": "uppercase", "flexGrow": "1",
    }),
    dbc.Button(
        DashIconify(icon="lucide:unfold-horizontal", width=13, color=C["text_dim"]),
        id="tree-expand-all", color="link", size="sm",
        style={"padding": "2px 4px", "border": "none"},
    ),
    dbc.Tooltip("Expand All", target="tree-expand-all"),
    dbc.Button(
        DashIconify(icon="lucide:fold-horizontal", width=13, color=C["text_dim"]),
        id="tree-collapse-all", color="link", size="sm",
        style={"padding": "2px 4px", "border": "none"},
    ),
    dbc.Tooltip("Collapse All", target="tree-collapse-all"),
], style={
    "display": "flex", "alignItems": "center",
    "padding": "8px 10px 4px",
    "borderBottom": f"1px solid {C['panel_bdr']}",
    "marginBottom": "4px",
})

project_tree = html.Div([
    tree_controls,

    # Dynamic room tree — populated by update_all callback
    html.Div(
        id="room-tree-container",
        style={"padding": "0 4px", "overflowY": "auto", "flexGrow": "1"},
    ),

    # AOI level indicator at bottom of tree
    html.Div([
        DashIconify(icon="lucide:layers-2", width=12, color=C["text_dim"],
                    style={"marginRight": "5px"}),
        html.Span("—", id="aoi-level-label", style={
            "fontSize": "10px", "fontFamily": FONT_MONO, "color": C["text_dim"],
            "flexGrow": "1",
        }),
        dbc.Button("Change", id="tree-aoi-level", color="link", size="sm",
                   style={"fontFamily": FONT_MONO, "fontSize": "10px",
                          "padding": "1px 5px", "color": C["accent2"],
                          "border": f"1px solid {C['panel_bdr']}",
                          "borderRadius": "3px"}),
    ], style={
        "display": "flex", "alignItems": "center",
        "padding": "6px 10px",
        "borderTop": f"1px solid {C['panel_bdr']}",
    }),

], id="project-tree-panel", style={
    "backgroundColor": C["panel_bg"],
    "borderRight": f"1px solid {C['panel_bdr']}",
    "display": "flex",
    "flexDirection": "column",
    "minWidth": "240px",
    "maxWidth": "300px",
    "height": "100%",
    "overflowY": "hidden",
})

# ----------------------------------------------------------------- right panel --
#
# Input controls panel – mirrors the matplotlib editor's input panel:
#   Parent Apartment selector, Room Name textbox, Room Type buttons,
#   Save / Delete action buttons, Status text, Name preview.

right_panel = html.Div([

    panel_card("Parent Apartment", html.Div([
        dbc.InputGroup([
            dbc.Button(
                DashIconify(icon="lucide:chevron-left", width=14),
                id="parent-prev", color="secondary", size="sm",
                style={"backgroundColor": C["deep"], "border": f"1px solid {C['panel_bdr']}",
                       "borderRight": "none", "borderRadius": "4px 0 0 4px"}),
            dbc.Input(
                id="input-parent",
                value="(None)",
                style={"fontSize": "11px", "fontFamily": FONT_MONO,
                       "backgroundColor": C["deep"], "color": C["text_sec"],
                       "border": f"1px solid {C['panel_bdr']}",
                       "borderLeft": "none", "borderRight": "none",
                       "textAlign": "center"},
            ),
            dbc.Button(
                DashIconify(icon="lucide:chevron-right", width=14),
                id="parent-next", color="secondary", size="sm",
                style={"backgroundColor": C["deep"], "border": f"1px solid {C['panel_bdr']}",
                       "borderLeft": "none", "borderRadius": "0 4px 4px 0"}),
        ], size="sm"),
    ])),

    panel_card("Room Name", html.Div([
        dbc.Input(
            id="input-room-name",
            placeholder="e.g. BED1  →  U101_BED1",
            debounce=True,
            style={"fontSize": "11px", "fontFamily": FONT_MONO,
                   "backgroundColor": C["deep"], "color": C["text_pri"],
                   "border": f"1px solid {C['panel_bdr']}",
                   "borderRadius": "4px", "marginBottom": "4px"},
        ),
        html.Div(id="room-name-preview", style={
            "fontSize": "10px", "fontFamily": FONT_MONO,
            "color": C["accent2"], "minHeight": "14px",
        }),
    ])),

    panel_card("Room Type", html.Div([
        html.Div([
            room_type_btn("BED",      "rt-bed",     active=True),
            room_type_btn("LIVING",   "rt-living"),
            room_type_btn("NON-RESI", "rt-nonresi"),
            room_type_btn("CIRC",     "rt-circ"),
        ], style={"display": "flex", "flexWrap": "wrap"}),
    ])),

    panel_card("Actions", html.Div([
        dbc.Row([
            dbc.Col(
                dbc.Button([
                    DashIconify(icon="lucide:save", width=14, style={"marginRight": "5px"}),
                    "Save", kbd("S"),
                ], id="btn-save-room", color="success", size="sm",
                   style={"width": "100%", "fontFamily": FONT_MONO, "fontSize": "11px",
                          "backgroundColor": "#d1fae5", "color": "#065f46", "border": "1px solid #059669"}),
                width=7,
            ),
            dbc.Col(
                dbc.Button([
                    DashIconify(icon="lucide:trash-2", width=14, style={"marginRight": "5px"}),
                    "Delete",
                ], id="btn-delete-room", color="danger", size="sm",
                   style={"width": "100%", "fontFamily": FONT_MONO, "fontSize": "11px",
                          "backgroundColor": "#fee2e2", "color": "#991b1b", "border": "1px solid #dc2626"}),
                width=5,
            ),
        ], className="g-2"),
    ])),

    # Status bar
    html.Div([
        html.Div(id="status-dot", style={
            "width": "6px", "height": "6px", "borderRadius": "50%",
            "backgroundColor": C["accent2"], "marginRight": "7px", "flexShrink": "0",
        }),
        html.Span("Status: Ready to draw", id="status-text", style={
            "fontSize": "11px", "fontFamily": FONT_MONO, "color": C["accent2"],
        }),
    ], style={
        "display": "flex", "alignItems": "center",
        "padding": "6px 10px",
        "backgroundColor": C["deep"],
        "borderRadius": "4px",
        "border": f"1px solid {C['panel_bdr']}",
        "marginBottom": "8px",
    }),

    # DF% results legend (hidden until results computed)
    html.Div([
        panel_label("DF% Results Legend"),
        html.Div([
            *[html.Div([
                html.Div(style={
                    "width": "10px", "height": "10px", "borderRadius": "2px",
                    "backgroundColor": bg, "marginRight": "6px", "flexShrink": "0",
                }),
                html.Span(lbl, style={
                    "fontSize": "10px", "fontFamily": FONT_MONO, "color": C["text_sec"],
                }),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "3px"})
            for bg, lbl in [
                ("#059669", "≥ threshold (pass)"),
                ("#d97706", "< threshold (marginal)"),
                ("#dc2626", "< 50 % of threshold (fail)"),
            ]],
        ], style={"padding": "4px 10px 6px"}),
    ], id="df-legend", style={
        "backgroundColor": C["panel_bg"],
        "border": f"1px solid {C['panel_bdr']}",
        "borderRadius": "6px",
        "marginBottom": "8px",
    }),

], style={
    "width": "220px",
    "minWidth": "200px",
    "height": "100%",
    "backgroundColor": C["panel_bg"],
    "borderLeft": f"1px solid {C['panel_bdr']}",
    "overflowY": "auto",
    "padding": "8px",
    "scrollbarWidth": "thin",
})

# --------------------------------------------------------------- viewport ----
#
# Viewport:
#   • Top toolbar: HDR navigation ▲▼, filename, variant badge, Undo, multi-select info
#   • Centre: dot-grid drafting canvas (placeholder for image/plotly figure)
#   • Bottom: progress bar

viewport = html.Div([

    # ---- Top viewport toolbar ----
    html.Div([
        # HDR navigation
        dbc.ButtonGroup([
            dbc.Button(
                DashIconify(icon="lucide:chevron-up", width=14),
                id="hdr-prev", color="secondary", size="sm",
                style={"backgroundColor": C["panel_bg"],
                       "border": f"1px solid {C['panel_bdr']}"},
            ),
            dbc.Button(
                DashIconify(icon="lucide:chevron-down", width=14),
                id="hdr-next", color="secondary", size="sm",
                style={"backgroundColor": C["panel_bg"],
                       "border": f"1px solid {C['panel_bdr']}"},
            ),
        ], style={"marginRight": "8px"}),
        dbc.Tooltip("Previous HDR  [↑]", target="hdr-prev"),
        dbc.Tooltip("Next HDR  [↓]",     target="hdr-next"),

        # Filename
        html.Span("level_01_north.hdr", id="hdr-filename", style={
            "fontSize": "11px", "fontFamily": FONT_MONO,
            "color": C["text_pri"], "marginRight": "8px",
        }),

        # Image variant badge (HDR / TIFF toggle)
        html.Span("HDR", id="variant-badge", style={
            "fontSize": "10px", "fontFamily": FONT_MONO,
            "color": C["accent"],
            "backgroundColor": C["btn_on"],
            "border": f"1px solid {C['accent']}",
            "borderRadius": "3px", "padding": "1px 6px",
            "marginRight": "12px", "cursor": "pointer",
        }),
        dbc.Tooltip("Toggle image variant  [T]", target="variant-badge"),

        # Floor index
        html.Span("1 / 4", id="hdr-index", style={
            "fontSize": "10px", "fontFamily": FONT_MONO, "color": C["text_dim"],
        }),

        html.Div(style={"flex": "1"}),

        # Undo
        dbc.Button([
            DashIconify(icon="lucide:undo-2", width=13,
                        style={"marginRight": "4px"}),
            "Undo", kbd("Ctrl+Z"),
        ], id="btn-undo", color="secondary", size="sm",
           style={"fontFamily": FONT_MONO, "fontSize": "10px",
                  "backgroundColor": C["panel_bg"],
                  "border": f"1px solid {C['panel_bdr']}",
                  "marginRight": "6px"}),

        # Fit to room
        dbc.Button([
            DashIconify(icon="lucide:expand", width=13, style={"marginRight": "4px"}),
            "Fit", kbd("F"),
        ], id="btn-fit", color="secondary", size="sm",
           style={"fontFamily": FONT_MONO, "fontSize": "10px",
                  "backgroundColor": C["panel_bg"],
                  "border": f"1px solid {C['panel_bdr']}",
                  "marginRight": "6px"}),

        # Select all
        dbc.Button([
            DashIconify(icon="lucide:check-square", width=13, style={"marginRight": "4px"}),
            "Select All", kbd("Ctrl+A"),
        ], id="btn-select-all", color="secondary", size="sm",
           style={"fontFamily": FONT_MONO, "fontSize": "10px",
                  "backgroundColor": C["panel_bg"],
                  "border": f"1px solid {C['panel_bdr']}"}),

    ], style={
        "display": "flex", "alignItems": "center",
        "padding": "6px 10px",
        "backgroundColor": C["header"],
        "borderBottom": f"1px solid {C['panel_bdr']}",
        "flexShrink": "0",
    }),

    # ---- Canvas area ----
    html.Div([

        # Live Plotly viewport
        dcc.Graph(
            id="viewport-graph",
            config={
                "scrollZoom": True,
                "displayModeBar": False,
                "doubleClick": "reset",
            },
            style={"height": "100%", "width": "100%"},
        ),

        # Floating drawing tool palette (bottom-centre, overlaid above the graph)
        html.Div([
            *[html.Div([
                DashIconify(icon=ic, width=14, color=C["text_sec"],
                            style={"marginRight": "8px"}),
                html.Span(lbl, style={"fontSize": "11px", "fontFamily": FONT_MONO,
                                      "color": C["text_sec"], "flexGrow": "1"}),
                kbd(k) if k else html.Span(),
            ], id=bid, style={
                "display": "flex", "alignItems": "center",
                "padding": "5px 12px",
                "borderBottom": f"1px solid {C['panel_bdr']}" if lbl != "Room Divider" else "none",
                "cursor": "pointer",
            }) for ic, lbl, k, bid in [
                ("lucide:git-commit-horizontal", "Draw Polygon",    "D",    "tool-draw"),
                ("lucide:scissors",              "Room Divider",    "DD",   "tool-divider"),
                ("lucide:pen-line",              "Edit Mode",       "E",    "tool-edit"),
                ("lucide:crosshair",             "DF% Placement",   "P",    "tool-dfplace"),
                ("lucide:search",                "Zoom",            None,   "tool-zoom"),
                ("lucide:move",                  "Pan",             None,   "tool-pan"),
                ("lucide:corner-down-right",     "Ortho Lines",     "O",    "tool-ortho"),
                ("lucide:undo-2",                "Undo Last",       "Ctrl+Z","tool-undo-fp"),
            ]],
        ], style={
            "position": "absolute", "bottom": "20px", "left": "50%",
            "transform": "translateX(-50%)",
            "backgroundColor": C["header"],
            "border": f"1px solid {C['panel_bdr']}",
            "borderRadius": "8px",
            "boxShadow": "0 4px 16px rgba(0,0,0,0.12)",
            "zIndex": 20,
            "minWidth": "200px",
            "pointerEvents": "auto",
        }),

        # Overlay alignment panel (top-right, shown only when align mode active)
        html.Div(
            id="overlay-align-panel",
            children=[
                html.Div("OVERLAY ALIGNMENT", style={
                    "fontSize": "9px", "fontFamily": FONT_MONO,
                    "color": C["text_dim"], "letterSpacing": "0.1em",
                    "marginBottom": "8px",
                }),
                html.Div([
                    html.Span("Offset X", style={"fontSize": "10px", "fontFamily": FONT_MONO,
                                                 "color": C["text_sec"], "width": "60px", "display": "inline-block"}),
                    dbc.Input(id="overlay-offset-x", type="number", value=0, step=1, debounce=True,
                              size="sm", style={"width": "80px", "fontFamily": FONT_MONO, "fontSize": "10px"}),
                ], style={"display": "flex", "alignItems": "center", "marginBottom": "4px"}),
                html.Div([
                    html.Span("Offset Y", style={"fontSize": "10px", "fontFamily": FONT_MONO,
                                                 "color": C["text_sec"], "width": "60px", "display": "inline-block"}),
                    dbc.Input(id="overlay-offset-y", type="number", value=0, step=1, debounce=True,
                              size="sm", style={"width": "80px", "fontFamily": FONT_MONO, "fontSize": "10px"}),
                ], style={"display": "flex", "alignItems": "center", "marginBottom": "4px"}),
                html.Div([
                    html.Span("Scale X", style={"fontSize": "10px", "fontFamily": FONT_MONO,
                                                "color": C["text_sec"], "width": "60px", "display": "inline-block"}),
                    dbc.Input(id="overlay-scale-x", type="number", value=1.0, step=0.01, debounce=True,
                              size="sm", style={"width": "80px", "fontFamily": FONT_MONO, "fontSize": "10px"}),
                ], style={"display": "flex", "alignItems": "center", "marginBottom": "4px"}),
                html.Div([
                    html.Span("Scale Y", style={"fontSize": "10px", "fontFamily": FONT_MONO,
                                                "color": C["text_sec"], "width": "60px", "display": "inline-block"}),
                    dbc.Input(id="overlay-scale-y", type="number", value=1.0, step=0.01, debounce=True,
                              size="sm", style={"width": "80px", "fontFamily": FONT_MONO, "fontSize": "10px"}),
                ], style={"display": "flex", "alignItems": "center", "marginBottom": "8px"}),
                html.Div([
                    html.Span("Alpha", style={"fontSize": "10px", "fontFamily": FONT_MONO,
                                              "color": C["text_sec"], "width": "60px", "display": "inline-block"}),
                    dbc.Input(id="overlay-alpha", type="number", value=0.6, step=0.05,
                              min=0.0, max=1.0, debounce=True,
                              size="sm", style={"width": "80px", "fontFamily": FONT_MONO, "fontSize": "10px"}),
                ], style={"display": "flex", "alignItems": "center"}),
            ],
            style={
                "display": "none",  # shown via callback when align mode active
                "position": "absolute", "top": "12px", "right": "12px",
                "backgroundColor": C["header"],
                "border": f"1px solid {C['panel_bdr']}",
                "borderRadius": "6px",
                "padding": "10px 12px",
                "boxShadow": "0 4px 16px rgba(0,0,0,0.12)",
                "zIndex": 30,
                "pointerEvents": "auto",
            },
        ),

        # Zoom indicator (bottom-right)
        html.Div("100%", id="zoom-indicator", style={
            "position": "absolute", "bottom": "12px", "right": "12px",
            "fontSize": "10px", "fontFamily": FONT_MONO, "color": C["text_dim"],
            "backgroundColor": C["header"], "border": f"1px solid {C['panel_bdr']}",
            "borderRadius": "4px", "padding": "2px 6px",
            "zIndex": 10,
            "pointerEvents": "none",
        }),

    ], style={
        "flexGrow": "1",
        "display": "flex",
        "position": "relative",
        "overflow": "hidden",
    }),

    # ---- Progress bar (hidden by default) ----
    html.Div([
        html.Div(id="progress-fill", style={
            "height": "100%",
            "width": "0%",
            "backgroundColor": C["accent"],
            "borderRadius": "3px",
            "transition": "width 0.2s ease",
        }),
        html.Span("", id="progress-text", style={
            "position": "absolute", "top": "50%", "left": "50%",
            "transform": "translate(-50%, -50%)",
            "fontSize": "10px", "fontFamily": FONT_MONO, "color": C["text_pri"],
        }),
    ], id="progress-bar-wrap", style={
        "height": "18px",
        "backgroundColor": C["deep"],
        "borderTop": f"1px solid {C['panel_bdr']}",
        "position": "relative",
        "flexShrink": "0",
        "display": "none",      # hidden until export starts
    }),

], style={
    "flexGrow": "1",
    "display": "flex",
    "flexDirection": "column",
    "backgroundColor": C["viewport"],
    "overflow": "hidden",
})

# --------------------------------------------------------------- bottom row --
#
# Model Validation + Simulation Manager panels, plus
# PDF Resolution, AOI Level, and Reset Level Alignment controls.

model_validation_panel = panel_card("Model Validation", html.Div([
    *[html.Div([
        DashIconify(icon=ic, width=12, color=clr, style={"marginRight": "7px", "flexShrink": "0"}),
        html.Span(lbl, style={"fontSize": "11px", "fontFamily": FONT_MONO, "color": C["text_sec"]}),
    ], style={"display": "flex", "alignItems": "center", "marginBottom": "5px"})
     for ic, lbl, clr in [
         ("lucide:zap",         "AcceleratedRT Preview",              C["accent"]),
         ("lucide:scan-search", "Preview simulation boundary checks", C["text_dim"]),
         ("lucide:brush",       "Cleaning tools",                     C["text_dim"]),
     ]],
    html.Div([
        DashIconify(icon="lucide:info", width=12, color=C["accent2"],
                    style={"marginRight": "6px", "flexShrink": "0"}),
        html.Span("Done here before Sun Merger", style={
            "fontSize": "10px", "fontFamily": FONT_MONO, "color": C["accent2"],
        }),
    ], style={
        "display": "flex", "alignItems": "center",
        "backgroundColor": "#eef4fe", "borderRadius": "4px",
        "padding": "5px 8px", "border": f"1px solid {C['accent2']}44",
    }),
]))

simulation_manager_panel = panel_card("Simulation Manager", html.Div([
    html.Div([
        html.Span("Scenario grid:", style={
            "fontSize": "11px", "fontFamily": FONT_MONO, "color": C["text_sec"],
            "display": "block", "marginBottom": "4px",
        }),
        dbc.Select(
            id="scenario-select",
            options=[{"label": "Default", "value": "default"},
                     {"label": "Summer Solstice", "value": "summer"},
                     {"label": "Winter Solstice", "value": "winter"},
                     {"label": "Equinox", "value": "equinox"}],
            value="default",
            style={"fontSize": "11px", "fontFamily": FONT_MONO,
                   "backgroundColor": C["deep"], "color": C["text_sec"],
                   "border": f"1px solid {C['panel_bdr']}",
                   "borderRadius": "4px", "marginBottom": "6px"},
        ),
    ]),
    action_btn("Review Simulation", "btn-review-sim",   "lucide:play-circle"),
    action_btn("Connect to Cloud",  "btn-cloud-connect","lucide:cloud-upload"),

    html.Div([
        html.Span("Compliance framework:", style={
            "fontSize": "11px", "fontFamily": FONT_MONO,
            "color": C["text_sec"], "display": "block", "marginBottom": "4px",
        }),
        html.Div([
            dbc.Select(
                id="compliance-framework",
                options=[
                    {"label": "BESS",      "value": "bess"},
                    {"label": "Green Star", "value": "greenstar"},
                    {"label": "NABERS",    "value": "nabers"},
                    {"label": "EN 17037",  "value": "en17037"},
                    {"label": "WELL",      "value": "well"},
                ],
                value="bess",
                style={"fontSize": "11px", "fontFamily": FONT_MONO,
                       "backgroundColor": C["deep"], "color": C["text_sec"],
                       "border": f"1px solid {C['panel_bdr']}",
                       "borderRadius": "4px 0 0 4px", "flexGrow": "1"},
            ),
            html.Div(
                DashIconify(icon="lucide:heart", width=14, color="#e05c7a"),
                style={"padding": "6px 10px", "backgroundColor": C["deep"],
                       "border": f"1px solid {C['panel_bdr']}",
                       "borderLeft": "none", "borderRadius": "0 4px 4px 0",
                       "cursor": "pointer"},
            ),
        ], style={"display": "flex"}),
    ]),
]))

# PDF resolution + AOI level + alignment controls
pdf_controls_panel = panel_card("Floor Plan Controls", html.Div([
    # PDF Resolution
    html.Div([
        html.Span("PDF Resolution:", style={
            "fontSize": "11px", "fontFamily": FONT_MONO,
            "color": C["text_sec"], "marginRight": "8px",
        }),
        dbc.RadioItems(
            id="pdf-dpi-radio",
            options=[
                {"label": "72",  "value": 72},
                {"label": "150", "value": 150},
                {"label": "300", "value": 300},
                {"label": "600", "value": 600},
            ],
            value=150,
            inline=True,
            style={"fontSize": "11px", "fontFamily": FONT_MONO, "color": C["text_sec"]},
        ),
    ], style={"display": "flex", "alignItems": "center", "marginBottom": "6px",
              "flexWrap": "wrap"}),

    html.Div([
        action_btn("Reset Level Alignment", "btn-reset-align", "lucide:rotate-ccw",
                   tip="Reset PDF overlay alignment for current HDR level"),
        action_btn("Change AOI Level",       "btn-aoi-level-bottom", "lucide:layers-2",
                   tip="Cycle IESVE FFL / AOI level assignment"),
    ]),
]))

bottom_row = html.Div([
    html.Div(model_validation_panel, style={"width": "320px", "marginRight": "10px"}),
    html.Div(simulation_manager_panel, style={"width": "280px", "marginRight": "10px"}),
    html.Div(pdf_controls_panel, style={"flex": "1", "minWidth": "220px"}),
], style={
    "display": "flex",
    "padding": "10px 14px",
    "backgroundColor": "#f5f6f7",
    "borderTop": f"1px solid {C['panel_bdr']}",
    "minHeight": "160px",
    "flexShrink": "0",
    "overflowX": "auto",
})

# ------------------------------------------------------------------- header --

header = html.Div([
    # Logo
    html.Span("Archilume", style={
        "fontFamily": FONT_HEAD, "fontWeight": "700", "fontSize": "17px",
        "color": C["text_pri"], "marginRight": "16px", "letterSpacing": "-0.02em",
    }),
    html.Div(style={"width": "1px", "height": "18px",
                    "backgroundColor": C["panel_bdr"], "marginRight": "16px"}),

    # Workflow / project name
    html.Span("HDR AOI Editor", id="workflow-name", style={
        "fontFamily": FONT_MONO, "fontSize": "11px",
        "color": C["text_sec"], "marginRight": "10px",
    }),

    # Project status badge
    html.Span("No project loaded", id="project-status", style={
        "fontFamily": FONT_MONO, "fontSize": "10px", "color": C["text_dim"],
        "backgroundColor": C["deep"], "padding": "2px 8px",
        "borderRadius": "3px", "border": f"1px solid {C['panel_bdr']}",
        "marginRight": "12px",
    }),

    # Mode indicators
    html.Span("DRAW", id="mode-badge-draw", style={
        "fontFamily": FONT_MONO, "fontSize": "9px",
        "color": C["accent"], "backgroundColor": C["btn_on"],
        "border": f"1px solid {C['accent']}",
        "borderRadius": "3px", "padding": "1px 6px", "marginRight": "4px",
        "display": "none",  # shown when draw mode active
    }),
    html.Span("EDIT", id="mode-badge-edit", style={
        "fontFamily": FONT_MONO, "fontSize": "9px",
        "color": "#92400e", "backgroundColor": "#fef3c7",
        "border": f"1px solid {C['warning']}",
        "borderRadius": "3px", "padding": "1px 6px", "marginRight": "4px",
        "display": "none",  # shown when edit mode active
    }),
    html.Span("DIVIDER", id="mode-badge-divider", style={
        "fontFamily": FONT_MONO, "fontSize": "9px",
        "color": "#1e40af", "backgroundColor": "#dbeafe",
        "border": f"1px solid {C['accent2']}",
        "borderRadius": "3px", "padding": "1px 6px", "marginRight": "4px",
        "display": "none",  # shown when divider mode active
    }),

    html.Div(style={"flex": "1"}),

    # Multi-select counter (hidden until rooms selected)
    html.Span("2 rooms selected", id="multiselect-badge", style={
        "fontFamily": FONT_MONO, "fontSize": "10px",
        "color": "#1e40af",
        "backgroundColor": "#dbeafe",
        "border": f"1px solid {C['accent2']}",
        "borderRadius": "3px", "padding": "2px 8px",
        "marginRight": "10px",
        "display": "none",
    }),

    # Keyboard shortcuts hint
    dbc.Button([
        DashIconify(icon="lucide:keyboard", width=13, style={"marginRight": "5px"}),
        "Shortcuts",
    ], id="btn-shortcuts", color="secondary", size="sm",
       style={"fontFamily": FONT_MONO, "fontSize": "10px",
              "backgroundColor": C["panel_bg"],
              "border": f"1px solid {C['panel_bdr']}"}),
    dbc.Tooltip("Show keyboard shortcut reference", target="btn-shortcuts"),

], style={
    "display": "flex", "alignItems": "center",
    "height": "46px",
    "backgroundColor": C["header"],
    "borderBottom": f"1px solid {C['panel_bdr']}",
    "paddingLeft": "14px",
    "paddingRight": "14px",
    "flexShrink": "0",
})

# ----------------------------------------------- keyboard shortcuts modal ----

shortcuts_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Keyboard Shortcuts", style={
        "fontFamily": FONT_MONO, "fontSize": "13px", "color": C["text_pri"],
    }), style={"backgroundColor": C["header"], "borderBottom": f"1px solid {C['panel_bdr']}"}),
    dbc.ModalBody([
        html.Div([
            *[html.Div([
                html.Div(k, style={
                    "fontFamily": FONT_MONO, "fontSize": "11px",
                    "color": C["accent2"],
                    "backgroundColor": C["deep"],
                    "border": f"1px solid {C['panel_bdr']}",
                    "borderRadius": "3px", "padding": "2px 8px",
                    "width": "120px", "flexShrink": "0", "marginRight": "12px",
                }),
                html.Span(desc, style={
                    "fontSize": "11px", "fontFamily": FONT_MONO,
                    "color": C["text_sec"],
                }),
            ], style={"display": "flex", "alignItems": "center",
                      "marginBottom": "6px", "padding": "3px 0",
                      "borderBottom": f"1px solid {C['panel_bdr']}22"})
             for k, desc in [
                 ("↑ / ↓",           "Navigate HDR files"),
                 ("T",               "Toggle image variant (HDR/TIFF)"),
                 ("D",               "Toggle draw mode"),
                 ("DD",              "Enter room divider mode (quick double-D)"),
                 ("E",               "Toggle edit mode"),
                 ("Click vertex",    "Select vertex for move (edit mode)"),
                 ("Click canvas",    "Move selected vertex to position"),
                 ("Delete/Backspace","Delete selected vertex (edit mode, ≥4 verts)"),
                 ("O",               "Toggle ortho lines"),
                 ("P",               "Toggle DF% placement mode"),
                 ("S",               "Save room / confirm divider"),
                 ("F",               "Fit zoom to selected room"),
                 ("R",               "Reset zoom"),
                 ("Ctrl+Z",          "Undo vertex move / draw step / room delete"),
                 ("Ctrl+A",          "Select all rooms on current HDR"),
                 ("Shift+S",         "Force save session"),
                 ("Ctrl+R",          "Rotate overlay 90°"),
                 ("Esc",             "Exit mode / align mode / deselect"),
             ]],
        ]),
    ], style={"backgroundColor": C["panel_bg"], "padding": "16px 20px"}),
    dbc.ModalFooter(
        dbc.Button("Close", id="shortcuts-modal-close", color="secondary", size="sm",
                   style={"fontFamily": FONT_MONO, "fontSize": "11px"}),
        style={"backgroundColor": C["header"], "borderTop": f"1px solid {C['panel_bdr']}"},
    ),
], id="shortcuts-modal", is_open=False, centered=True,
   style={"fontFamily": FONT_MONO})

# ------------------------------------------------------------------ layout ---

app.layout = html.Div([
    # Hidden stores & polling interval
    dcc.Store(id="store-trigger", data=0),
    dcc.Store(id="store-draw-vertices", data=[]),
    dcc.Store(id="store-divider-points", data=[]),
    dcc.Store(id="keyboard-event", data=""),
    dcc.Store(id="store-grid-spacing", data=50),
    dcc.Store(id="store-grid-visible", data=True),
    dcc.Interval(id="keyboard-poll", interval=150, n_intervals=0),
    dcc.Interval(id="export-poll", interval=400, disabled=True, n_intervals=0),

    # Fixed left sidebar
    left_sidebar,

    # Main content (offset by sidebar width)
    html.Div([
        header,

        # Middle row: project tree | viewport | right panel
        html.Div([
            project_tree,
            viewport,
            right_panel,
        ], style={
            "display": "flex",
            "flex": "1",
            "overflow": "hidden",
            "minHeight": "0",       # allow flex children to shrink
        }),

        # Bottom panels
        bottom_row,

    ], style={
        "marginLeft": "52px",
        "display": "flex",
        "flexDirection": "column",
        "height": "100vh",
        "overflow": "hidden",
    }),

    # Modals & overlays
    shortcuts_modal,

    # Open Project modal
    dbc.Modal([
        dbc.ModalHeader("Open Project"),
        dbc.ModalBody([
            html.Div("Select a project to open:", style={
                "fontFamily": FONT_MONO, "fontSize": "11px",
                "color": C["text_sec"], "marginBottom": "8px",
            }),
            dbc.Select(
                id="open-project-select",
                options=[],
                placeholder="— choose project —",
                style={"fontFamily": FONT_MONO, "fontSize": "11px"},
            ),
        ]),
        dbc.ModalFooter([
            dbc.Button("Open", id="btn-open-project-confirm", color="primary", size="sm",
                       style={"fontFamily": FONT_MONO, "fontSize": "11px", "marginRight": "8px"}),
            dbc.Button("Cancel", id="btn-open-project-cancel", color="secondary", size="sm",
                       style={"fontFamily": FONT_MONO, "fontSize": "11px"}),
        ]),
    ], id="open-project-modal", is_open=False),

    # Create Project modal
    dbc.Modal([
        dbc.ModalHeader("Create New Project"),
        dbc.ModalBody([
            html.Div("Project name:", style={
                "fontFamily": FONT_MONO, "fontSize": "11px",
                "color": C["text_sec"], "marginBottom": "6px",
            }),
            dbc.Input(
                id="create-project-name",
                placeholder="e.g. MyProject",
                debounce=False,
                style={"fontFamily": FONT_MONO, "fontSize": "11px", "marginBottom": "8px"},
            ),
            html.Div(id="create-project-feedback", style={
                "fontFamily": FONT_MONO, "fontSize": "10px",
                "color": C["danger"], "minHeight": "14px",
            }),
        ]),
        dbc.ModalFooter([
            dbc.Button("Create", id="btn-create-project-confirm", color="success", size="sm",
                       style={"fontFamily": FONT_MONO, "fontSize": "11px", "marginRight": "8px"}),
            dbc.Button("Cancel", id="btn-create-project-cancel", color="secondary", size="sm",
                       style={"fontFamily": FONT_MONO, "fontSize": "11px"}),
        ]),
    ], id="create-project-modal", is_open=False),

    # Extract archive modal
    dbc.Modal([
        dbc.ModalHeader("Extract Archive"),
        dbc.ModalBody([
            html.Div("Select an archive to restore:", style={
                "fontFamily": FONT_MONO, "fontSize": "11px",
                "color": C["text_sec"], "marginBottom": "8px",
            }),
            dbc.Select(
                id="extract-archive-select",
                options=[],
                placeholder="— choose archive —",
                style={"fontFamily": FONT_MONO, "fontSize": "11px", "marginBottom": "8px"},
            ),
            html.Div(
                "This will overwrite the current project AOI files and reload the session.",
                style={"fontFamily": FONT_MONO, "fontSize": "10px", "color": C["danger"]},
            ),
        ]),
        dbc.ModalFooter([
            dbc.Button("Extract & Reload", id="btn-extract-confirm", color="danger", size="sm",
                       style={"fontFamily": FONT_MONO, "fontSize": "11px", "marginRight": "8px"}),
            dbc.Button("Cancel", id="btn-extract-cancel", color="secondary", size="sm",
                       style={"fontFamily": FONT_MONO, "fontSize": "11px"}),
        ]),
    ], id="extract-modal", is_open=False),

], style={
    "display": "flex",
    "fontFamily": FONT_MONO,
    "backgroundColor": C["deep"],
    "color": C["text_pri"],
    "height": "100vh",
    "width": "100vw",
    "overflow": "hidden",
})

# ═══════════════════════════════════════════════════════════════════════════════
# Callbacks
# ═══════════════════════════════════════════════════════════════════════════════

# ── Keyboard capture (clientside) ────────────────────────────────────────────
# keyboard.js in assets/ sets window._lastKeyEvent on every keydown.
# We poll it every 150 ms and clear after reading.

app.clientside_callback(
    """
    function(n) {
        const ev = window._lastKeyEvent;
        window._lastKeyEvent = null;
        return ev ? JSON.stringify(ev) : "";
    }
    """,
    Output("keyboard-event", "data"),
    Input("keyboard-poll", "n_intervals"),
)


# ── Master render ─────────────────────────────────────────────────────────────

@app.callback(
    Output("viewport-graph", "figure", allow_duplicate=True),
    Output("hdr-filename", "children"),
    Output("hdr-index", "children"),
    Output("variant-badge", "children"),
    Output("room-tree-container", "children"),
    Output("status-text", "children", allow_duplicate=True),
    Output("mode-badge-draw", "style"),
    Output("mode-badge-edit", "style"),
    Output("mode-badge-divider", "style"),
    Output("project-status", "children", allow_duplicate=True),
    Output("aoi-level-label", "children"),
    Output("status-dot", "style"),
    Output("multiselect-badge", "children"),
    Output("multiselect-badge", "style"),
    Output("df-legend", "style"),
    Input("store-trigger", "data"),
    State("store-grid-spacing", "data"),
    State("store-grid-visible", "data"),
    prevent_initial_call=False,
)
def update_all(_trigger, grid_spacing, grid_visible):
    _badge_hidden = {"display": "none"}

    def _badge_visible(base_style):
        s = dict(base_style)
        s["display"] = "inline-block"
        return s

    DRAW_BASE = {
        "fontFamily": FONT_MONO, "fontSize": "9px",
        "color": C["accent"], "backgroundColor": C["btn_on"],
        "border": f"1px solid {C['accent']}",
        "borderRadius": "3px", "padding": "1px 6px", "marginRight": "4px",
    }
    EDIT_BASE = {
        "fontFamily": FONT_MONO, "fontSize": "9px",
        "color": "#92400e", "backgroundColor": "#fef3c7",
        "border": f"1px solid {C['warning']}",
        "borderRadius": "3px", "padding": "1px 6px", "marginRight": "4px",
    }
    DIV_BASE = {
        "fontFamily": FONT_MONO, "fontSize": "9px",
        "color": "#1e40af", "backgroundColor": "#dbeafe",
        "border": f"1px solid {C['accent2']}",
        "borderRadius": "3px", "padding": "1px 6px", "marginRight": "4px",
    }

    _dot_base = {"width": "6px", "height": "6px", "borderRadius": "50%",
                 "marginRight": "7px", "flexShrink": "0"}
    _multisel_hidden = {
        "fontFamily": FONT_MONO, "fontSize": "10px", "color": "#1e40af",
        "backgroundColor": "#dbeafe", "border": f"1px solid {C['accent2']}",
        "borderRadius": "3px", "padding": "2px 8px", "marginRight": "10px",
        "display": "none",
    }
    _df_legend_hidden = {"display": "none"}
    _df_legend_visible = {
        "backgroundColor": C["panel_bg"], "border": f"1px solid {C['panel_bdr']}",
        "borderRadius": "6px", "marginBottom": "8px",
    }

    if STATE is None:
        return (
            go.Figure(), "No images", "—", "HDR",
            [], "No project loaded",
            _badge_hidden, _badge_hidden, _badge_hidden,
            "No project loaded", "—",
            dict(_dot_base, backgroundColor=C["text_dim"]),
            "", _multisel_hidden, _df_legend_hidden,
        )

    fig = build_figure(
        grid_spacing=grid_spacing or 50,
        grid_visible=grid_visible if grid_visible is not None else True,
        state=STATE,
    )
    hdr_name = STATE.current_hdr_name or "No images"
    n_hdrs = len(STATE.hdr_files)
    idx_str = f"{STATE.current_hdr_idx + 1} / {n_hdrs}" if n_hdrs else "—"

    variant_label = "HDR"
    if STATE.image_variants:
        vp = STATE.current_variant_path
        if vp:
            suffix = vp.suffix.lower()
            if suffix in (".tif", ".tiff"):
                variant_label = "TIFF"
            elif suffix in (".png",):
                variant_label = "PNG"

    tree = render_tree(state=STATE)

    n_rooms = sum(1 for r in STATE.rooms if STATE._is_room_on_current_hdr(r))
    mode_str = (
        "DRAW" if STATE.draw_mode
        else "DIVIDER" if STATE.divider_mode
        else "EDIT" if STATE.edit_mode
        else "SELECT"
    )
    status = f"{hdr_name} | {n_rooms} rooms | {mode_str}"
    proj_label = STATE.project or "No project"

    draw_style = _badge_visible(DRAW_BASE) if STATE.draw_mode else _badge_hidden
    edit_style = _badge_visible(EDIT_BASE) if STATE.edit_mode else _badge_hidden
    div_style  = _badge_visible(DIV_BASE) if STATE.divider_mode else _badge_hidden

    # AOI level label
    aoi_label = STATE.get_aoi_level_label()

    # Status dot colour: teal = select, amber = edit/draw/divider, red = placement
    if STATE.placement_mode:
        dot_color = C["danger"]
    elif STATE.draw_mode or STATE.edit_mode or STATE.divider_mode:
        dot_color = C["warning"]
    else:
        dot_color = C["accent2"]
    dot_style = dict(_dot_base, backgroundColor=dot_color)

    # Multiselect badge
    n_sel = len(STATE.multi_selected_room_idxs)
    if n_sel > 0:
        ms_children = f"{n_sel} rooms selected"
        ms_style = dict(_multisel_hidden, display="inline-block")
    else:
        ms_children = ""
        ms_style = _multisel_hidden

    # DF legend: show when any stamps exist for current HDR
    hdr_name_cur = STATE.current_hdr_name or ""
    df_legend_style = (
        _df_legend_visible
        if STATE._df_stamps.get(hdr_name_cur)
        else _df_legend_hidden
    )

    return (
        fig, hdr_name, idx_str, variant_label,
        tree, status,
        draw_style, edit_style, div_style,
        proj_label, aoi_label, dot_style,
        ms_children, ms_style, df_legend_style,
    )


# ── DF compute trigger (fires after HDR nav) ──────────────────────────────────

def _trigger_df_compute() -> None:
    """Load DF image and compute compliance for current HDR in background."""
    if STATE is None:
        return
    # threading imported at top
    def _worker():
        STATE.load_df_image()
        STATE._compute_all_room_df_results()
    threading.Thread(target=_worker, daemon=True).start()


# ── HDR navigation ────────────────────────────────────────────────────────────

@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Input("hdr-prev", "n_clicks"),
    prevent_initial_call=True,
)
def hdr_prev(_):
    if STATE and STATE.current_hdr_idx > 0:
        STATE.current_hdr_idx -= 1
        STATE._rebuild_image_variants()
        STATE._rebuild_snap_arrays()
        STATE._update_parent_options()
        STATE.selected_room_idx = None
        STATE._edit_selected_vertex = None
        _trigger_df_compute()
    return time.time()


@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Input("hdr-next", "n_clicks"),
    prevent_initial_call=True,
)
def hdr_next(_):
    if STATE and STATE.hdr_files and STATE.current_hdr_idx < len(STATE.hdr_files) - 1:
        STATE.current_hdr_idx += 1
        STATE._rebuild_image_variants()
        STATE._rebuild_snap_arrays()
        STATE._update_parent_options()
        STATE.selected_room_idx = None
        STATE._edit_selected_vertex = None
        _trigger_df_compute()
    return time.time()


# ── Image variant toggle [T] ──────────────────────────────────────────────────

@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Input("variant-badge", "n_clicks"),
    Input("sb-image-toggle", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_variant(_, __):
    if STATE and STATE.image_variants:
        STATE.current_variant_idx = (STATE.current_variant_idx + 1) % len(STATE.image_variants)
    return time.time()


# ── Keyboard handler ──────────────────────────────────────────────────────────

_last_d_time: float = 0.0  # for DD double-key detection


@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Output("store-draw-vertices", "data", allow_duplicate=True),
    Input("keyboard-event", "data"),
    State("store-draw-vertices", "data"),
    prevent_initial_call=True,
)
def on_keyboard(key_json, draw_verts):
    global _last_d_time
    if not key_json or STATE is None:
        return no_update, no_update
    try:
        evt = json.loads(key_json)
    except (json.JSONDecodeError, TypeError):
        return no_update, no_update
    key = evt.get("key", "")
    ctrl = evt.get("ctrl", False)
    shift = evt.get("shift", False)
    trigger = no_update
    dv = no_update

    if key == "Escape":
        if STATE.overlay_align_mode:
            STATE.overlay_align_mode = False
        STATE.draw_mode = False
        STATE.edit_mode = False
        STATE.divider_mode = False
        STATE._divider_points = []
        STATE._divider_room_idx = None
        STATE.current_polygon_vertices = []
        STATE._edit_selected_vertex = None
        trigger = time.time()
        dv = []

    elif key.lower() == "d" and not ctrl and not shift:
        now = time.time()
        if now - _last_d_time < 0.4:
            # DD — enter divider mode on selected room
            _last_d_time = 0.0
            if not STATE.divider_mode:
                if not STATE.edit_mode:
                    STATE.edit_mode = True
                if STATE.selected_room_idx is not None:
                    STATE.divider_mode = True
                    STATE._divider_room_idx = STATE.selected_room_idx
                    STATE._divider_points = []
            STATE.draw_mode = False
        else:
            # Single D — draw mode toggle
            _last_d_time = now
            STATE.draw_mode = not STATE.draw_mode
            if STATE.draw_mode:
                STATE.edit_mode = False
                STATE.divider_mode = False
            STATE.current_polygon_vertices = []
            dv = []
        trigger = time.time()

    elif key.lower() == "e" and not ctrl:
        STATE.edit_mode = not STATE.edit_mode
        if not STATE.edit_mode:
            STATE.divider_mode = False
            STATE._divider_points = []
            STATE._edit_selected_vertex = None
        STATE.draw_mode = False
        trigger = time.time()

    elif key == "S" and shift and not ctrl:
        # Shift+S — force save session
        STATE._save_session()
        trigger = time.time()

    elif key.lower() == "s" and not ctrl and not shift:
        if STATE.divider_mode and STATE._divider_points:
            msg = STATE.finalize_division()
            print(msg)
            trigger = time.time()
            dv = []
        elif STATE.draw_mode and STATE.current_polygon_vertices:
            msg = STATE.save_room("ROOM")
            print(msg)
            trigger = time.time()
            dv = []

    elif key.lower() == "o":
        STATE.ortho_mode = not STATE.ortho_mode
        trigger = time.time()

    elif key.lower() == "z" and ctrl:
        if STATE.draw_mode:
            STATE.undo_draw()
            dv = [[v[0], v[1]] for v in STATE.current_polygon_vertices]
        else:
            STATE.undo_edit()
        trigger = time.time()

    elif key in ("Delete", "Backspace"):
        if STATE.divider_mode and STATE._divider_points:
            # Undo last divider point
            STATE._divider_points.pop()
            trigger = time.time()
        elif STATE.edit_mode and STATE._edit_selected_vertex is not None:
            r_idx, v_idx = STATE._edit_selected_vertex
            msg = STATE.delete_vertex(r_idx, v_idx)
            print(msg)
            trigger = time.time()
        elif STATE.draw_mode and STATE.current_polygon_vertices:
            # Undo last drawn vertex
            STATE.current_polygon_vertices.pop()
            dv = [[v[0], v[1]] for v in STATE.current_polygon_vertices]
            trigger = time.time()

    elif key == "ArrowUp":
        if STATE.overlay_align_mode:
            STATE.nudge_overlay("up")
            trigger = time.time()
        elif STATE.current_hdr_idx > 0:
            STATE.current_hdr_idx -= 1
            STATE._rebuild_image_variants()
            STATE._rebuild_snap_arrays()
            STATE._update_parent_options()
            STATE.selected_room_idx = None
            STATE._edit_selected_vertex = None
            trigger = time.time()

    elif key == "ArrowDown":
        if STATE.overlay_align_mode:
            STATE.nudge_overlay("down")
            trigger = time.time()
        elif STATE.hdr_files and STATE.current_hdr_idx < len(STATE.hdr_files) - 1:
            STATE.current_hdr_idx += 1
            STATE._rebuild_image_variants()
            STATE._rebuild_snap_arrays()
            STATE._update_parent_options()
            STATE.selected_room_idx = None
            STATE._edit_selected_vertex = None
            trigger = time.time()

    elif key == "ArrowLeft":
        if STATE.overlay_align_mode:
            STATE.nudge_overlay("left")
            trigger = time.time()

    elif key == "ArrowRight":
        if STATE.overlay_align_mode:
            STATE.nudge_overlay("right")
            trigger = time.time()

    elif key.lower() == "t":
        if STATE.image_variants:
            STATE.current_variant_idx = (STATE.current_variant_idx + 1) % len(STATE.image_variants)
            trigger = time.time()

    elif key.lower() == "p" and not ctrl:
        STATE.placement_mode = not STATE.placement_mode
        if STATE.placement_mode:
            # threading imported at top
            threading.Thread(target=STATE.load_df_image, daemon=True).start()
        trigger = time.time()

    elif key.lower() == "r" and ctrl:
        # Ctrl+R — rotate overlay 90°
        if STATE._overlay_visible:
            STATE.rotate_overlay_90()
        trigger = time.time()

    elif key.lower() == "r" and not ctrl:
        trigger = time.time()  # reset zoom — update_all rebuilds with autorange

    return trigger, dv


# Keyboard F → fire btn-fit
@app.callback(
    Output("btn-fit", "n_clicks", allow_duplicate=True),
    Input("keyboard-event", "data"),
    State("btn-fit", "n_clicks"),
    prevent_initial_call=True,
)
def keyboard_fit(key_json, n):
    if not key_json:
        return no_update
    try:
        evt = json.loads(key_json)
    except Exception:
        return no_update
    if evt.get("key", "").lower() == "f" and not evt.get("ctrl") and not evt.get("shift"):
        return (n or 0) + 1
    return no_update


# Keyboard Ctrl+A → fire btn-select-all
@app.callback(
    Output("btn-select-all", "n_clicks", allow_duplicate=True),
    Input("keyboard-event", "data"),
    State("btn-select-all", "n_clicks"),
    prevent_initial_call=True,
)
def keyboard_select_all(key_json, n):
    if not key_json:
        return no_update
    try:
        evt = json.loads(key_json)
    except Exception:
        return no_update
    if evt.get("key", "").lower() == "a" and evt.get("ctrl"):
        return (n or 0) + 1
    return no_update


# ── Reset zoom ────────────────────────────────────────────────────────────────

@app.callback(
    Output("viewport-graph", "figure", allow_duplicate=True),
    Input("sb-reset-zoom", "n_clicks"),
    State("store-grid-spacing", "data"),
    State("store-grid-visible", "data"),
    prevent_initial_call=True,
)
def reset_zoom(_, grid_spacing, grid_visible):
    return build_figure(
        grid_spacing=grid_spacing or 50,
        grid_visible=grid_visible if grid_visible is not None else True,
        state=STATE,
    )


# ── Shortcuts modal ───────────────────────────────────────────────────────────

@app.callback(
    Output("shortcuts-modal", "is_open"),
    Input("btn-shortcuts", "n_clicks"),
    Input("shortcuts-modal-close", "n_clicks"),
    State("shortcuts-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_shortcuts_modal(open_clicks, close_clicks, is_open):
    return not is_open


# ── Room name preview ─────────────────────────────────────────────────────────

@app.callback(
    Output("room-name-preview", "children"),
    Input("input-room-name", "value"),
    State("input-parent", "value"),
    prevent_initial_call=True,
)
def update_name_preview(name, parent):
    if not name:
        return ""
    parent = parent or ""
    if parent and parent != "(None)" and not name.startswith(parent + "_"):
        full = f"{parent}_{name}"
    else:
        full = name
    return f"Will save as: {full}"


# ── Open Project modal ────────────────────────────────────────────────────────

@app.callback(
    Output("open-project-modal", "is_open"),
    Output("open-project-select", "options"),
    Output("open-project-select", "value"),
    Input("sb-open-project", "n_clicks"),
    Input("btn-open-project-cancel", "n_clicks"),
    State("open-project-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_open_project(open_clicks, cancel_clicks, is_open):
    # list_projects imported at top
    triggered = ctx.triggered_id
    if triggered == "sb-open-project":
        projects = list_projects()
        options = [{"label": p, "value": p} for p in projects]
        current = STATE.project if STATE else None
        return True, options, current
    return False, [], None


@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Output("open-project-modal", "is_open", allow_duplicate=True),
    Output("project-status", "children", allow_duplicate=True),
    Input("btn-open-project-confirm", "n_clicks"),
    State("open-project-select", "value"),
    prevent_initial_call=True,
)
def confirm_open_project(_, project_name):
    if not project_name:
        return no_update, True, no_update
    # set_last_project imported at top
    set_last_project(project_name)
    _init_state(project_name)
    return time.time(), False, project_name


# ── Create Project modal ──────────────────────────────────────────────────────

@app.callback(
    Output("create-project-modal", "is_open"),
    Output("create-project-name", "value"),
    Input("sb-create-project", "n_clicks"),
    Input("btn-create-project-cancel", "n_clicks"),
    State("create-project-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_create_project(open_clicks, cancel_clicks, is_open):
    triggered = ctx.triggered_id
    if triggered == "sb-create-project":
        return True, ""
    return False, no_update


@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Output("create-project-modal", "is_open", allow_duplicate=True),
    Output("create-project-feedback", "children"),
    Input("btn-create-project-confirm", "n_clicks"),
    State("create-project-name", "value"),
    prevent_initial_call=True,
)
def confirm_create_project(_, project_name):
    if not project_name or not project_name.strip():
        return no_update, True, "Please enter a project name."
    name = project_name.strip()
    # Validate: only alphanumeric, hyphens, underscores
    # re imported at top
    if not re.match(r'^[\w\-]+$', name):
        return no_update, True, "Name may only contain letters, numbers, hyphens, underscores."
    # project_config imported at top
    if name in list_projects():
        return no_update, True, f"Project '{name}' already exists — use Open instead."
    # Create minimal project.toml
    save_project_toml(name, {"project": {"mode": "archilume"}})
    set_last_project(name)
    _init_state(name)
    return time.time(), False, ""


# ── Draw mode toggle (tool-draw button) ──────────────────────────────────────

@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Input("tool-draw", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_draw(_):
    if STATE is None:
        return no_update
    STATE.draw_mode = not STATE.draw_mode
    if STATE.draw_mode:
        STATE.edit_mode = False
        STATE.divider_mode = False
        STATE._divider_points = []
    STATE.current_polygon_vertices = []
    return time.time()


# ── Edit mode toggle ──────────────────────────────────────────────────────────

@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Input("sb-edit-mode", "n_clicks"),
    Input("tool-edit", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_edit(_, __):
    if STATE is None:
        return no_update
    STATE.edit_mode = not STATE.edit_mode
    if not STATE.edit_mode:
        STATE.divider_mode = False
        STATE._divider_points = []
    STATE.draw_mode = False
    return time.time()


# ── Ortho toggle ──────────────────────────────────────────────────────────────

@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Input("sb-ortho", "n_clicks"),
    Input("tool-ortho", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_ortho(_, __):
    if STATE is None:
        return no_update
    STATE.ortho_mode = not STATE.ortho_mode
    return time.time()


# ── Divider mode toggle ───────────────────────────────────────────────────────

@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Input("tool-divider", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_divider(_):
    if STATE is None:
        return no_update
    if STATE.divider_mode:
        STATE.divider_mode = False
        STATE._divider_points = []
        STATE._divider_room_idx = None
    else:
        if not STATE.edit_mode:
            STATE.edit_mode = True
        if STATE.selected_room_idx is not None:
            STATE.divider_mode = True
            STATE._divider_room_idx = STATE.selected_room_idx
            STATE._divider_points = []
    return time.time()


# ── Canvas click → vertex placement / room selection / vertex move ────────────

@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Output("store-draw-vertices", "data", allow_duplicate=True),
    Output("input-parent", "value", allow_duplicate=True),
    Input("viewport-graph", "clickData"),
    State("store-draw-vertices", "data"),
    prevent_initial_call=True,
)
def on_canvas_click(click_data, draw_verts):
    if STATE is None or click_data is None:
        return no_update, no_update, no_update
    pt = click_data.get("points", [{}])[0]
    x, y = pt.get("x"), pt.get("y")

    customdata = pt.get("customdata")
    if isinstance(customdata, list) and customdata:
        customdata = customdata[0]

    # ── Placement mode (DF% stamping) ─────────────────────────────────────────
    if STATE.placement_mode:
        if x is None or y is None:
            return no_update, no_update, no_update
        if isinstance(customdata, dict) and "stamp_idx" in customdata:
            STATE.remove_nearest_stamp(x, y)
            return time.time(), no_update, no_update
        if STATE._df_image is None:
            STATE.load_df_image()
        df_val = STATE.stamp_df(x, y)
        if df_val is not None:
            print(f"DF stamp: ({x:.0f}, {y:.0f}) = {df_val:.2f}%")
        return time.time(), no_update, no_update

    # ── Edit mode ─────────────────────────────────────────────────────────────
    if STATE.edit_mode and not STATE.divider_mode and not STATE.draw_mode:
        if isinstance(customdata, dict) and "vertex_idx" in customdata:
            room_idx = customdata["room_idx"]
            vertex_idx = customdata["vertex_idx"]
            if STATE._edit_selected_vertex == (room_idx, vertex_idx):
                STATE._edit_selected_vertex = None
            else:
                STATE._edit_selected_vertex = (room_idx, vertex_idx)
            return time.time(), no_update, no_update

        if STATE._edit_selected_vertex is not None and x is not None and y is not None:
            r_idx, v_idx = STATE._edit_selected_vertex
            sx, sy = STATE._snap_to_pixel(x, y)
            sx, sy = STATE._snap_to_vertex(sx, sy)
            if STATE.ortho_mode:
                verts = STATE.rooms[r_idx]["vertices"]
                prev_v = verts[(v_idx - 1) % len(verts)]
                next_v = verts[(v_idx + 1) % len(verts)]
                dx_p, dy_p = abs(sx - prev_v[0]), abs(sy - prev_v[1])
                dx_n, dy_n = abs(sx - next_v[0]), abs(sy - next_v[1])
                if min(dx_p, dy_p) < min(dx_n, dy_n):
                    ref = prev_v
                    if dx_p >= dy_p:
                        sy = ref[1]
                    else:
                        sx = ref[0]
            msg = STATE.move_vertex(r_idx, v_idx, sx, sy)
            print(msg)
            return time.time(), no_update, no_update

        if isinstance(customdata, dict) and "room_idx" in customdata and "vertex_idx" not in customdata:
            room_idx = customdata["room_idx"]
            if 0 <= room_idx < len(STATE.rooms):
                STATE.selected_room_idx = room_idx
                STATE.selected_parent = STATE.rooms[room_idx].get("parent")
                STATE._edit_selected_vertex = None
            return time.time(), no_update, no_update

        if x is not None:
            STATE._edit_selected_vertex = None
            return time.time(), no_update, no_update

        return no_update, no_update, no_update

    # ── Select-mode room click (non-edit, non-draw) ───────────────────────────
    if isinstance(customdata, dict) and "room_idx" in customdata:
        room_idx = customdata["room_idx"]
        if not STATE.divider_mode and not STATE.draw_mode:
            if 0 <= room_idx < len(STATE.rooms):
                STATE.selected_room_idx = room_idx
                STATE.selected_parent = STATE.rooms[room_idx].get("parent")
                return time.time(), no_update, no_update
        if x is None and "bbox" in pt:
            bbox = pt["bbox"]
            x = (bbox.get("x0", 0) + bbox.get("x1", 0)) / 2
            y = (bbox.get("y0", 0) + bbox.get("y1", 0)) / 2

    if x is None or y is None:
        return no_update, no_update, no_update

    # ── Divider mode ──────────────────────────────────────────────────────────
    if STATE.divider_mode:
        STATE.add_divider_point(x, y)
        return time.time(), no_update, no_update

    # ── Draw mode ─────────────────────────────────────────────────────────────
    if STATE.draw_mode:
        sx, sy = STATE._snap_to_pixel(x, y)
        # Try vertex snap first, then edge snap as fallback
        snapped_v = STATE._snap_to_vertex(sx, sy)
        if snapped_v == (sx, sy):
            sx, sy = STATE._snap_to_edge(sx, sy)
        else:
            sx, sy = snapped_v
        if STATE.ortho_mode and STATE.current_polygon_vertices:
            lx, ly = STATE.current_polygon_vertices[-1]
            dx, dy = abs(sx - lx), abs(sy - ly)
            if dx >= dy:
                sy = ly
            else:
                sx = lx
        STATE.current_polygon_vertices.append([sx, sy])
        # Auto-detect parent on first vertex
        parent_val = no_update
        if len(STATE.current_polygon_vertices) == 1 and STATE.selected_parent is None:
            detected = STATE.find_parent_at(sx, sy)
            if detected:
                STATE.selected_parent = detected
                parent_val = detected
        return time.time(), [[v[0], v[1]] for v in STATE.current_polygon_vertices], parent_val

    # ── Select mode ───────────────────────────────────────────────────────────
    room_idx = STATE.find_room_at(x, y)
    if room_idx is not None:
        STATE.selected_room_idx = room_idx
        STATE.selected_parent = STATE.rooms[room_idx].get("parent")
    else:
        STATE.selected_room_idx = None
        STATE.selected_parent = None
    return time.time(), no_update, no_update


# ── Save room ─────────────────────────────────────────────────────────────────

@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Output("store-draw-vertices", "data", allow_duplicate=True),
    Input("btn-save-room", "n_clicks"),
    State("input-room-name", "value"),
    State("input-parent", "value"),
    prevent_initial_call=True,
)
def on_save(_n, name, parent):
    if STATE is None:
        return no_update, no_update
    # Sync parent selection from the input field
    if parent and parent != "(None)":
        STATE.selected_parent = parent
    # Finalize divider
    if STATE.divider_mode:
        msg = STATE.finalize_division()
        print(msg)
        return time.time(), []
    # Save polygon
    if STATE.draw_mode and STATE.current_polygon_vertices:
        msg = STATE.save_room(name or "ROOM")
        print(msg)
        return time.time(), []
    return no_update, no_update


# ── Delete room ───────────────────────────────────────────────────────────────

@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Input("btn-delete-room", "n_clicks"),
    prevent_initial_call=True,
)
def on_delete(_n):
    if STATE is None:
        return no_update
    # Multi-select: delete all selected rooms (highest index first to preserve indices)
    targets = sorted(STATE.multi_selected_room_idxs, reverse=True)
    if not targets and STATE.selected_room_idx is not None:
        targets = [STATE.selected_room_idx]
    if not targets:
        return no_update
    for idx in targets:
        if 0 <= idx < len(STATE.rooms):
            STATE.delete_room(idx)
    STATE.multi_selected_room_idxs.clear()
    STATE.selected_room_idx = None
    return time.time()


# ── Undo ──────────────────────────────────────────────────────────────────────

@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Output("store-draw-vertices", "data", allow_duplicate=True),
    Input("btn-undo", "n_clicks"),
    prevent_initial_call=True,
)
def on_undo(_):
    if STATE is None:
        return no_update, no_update
    if STATE.draw_mode and STATE.current_polygon_vertices:
        STATE.current_polygon_vertices.pop()
        return time.time(), [[v[0], v[1]] for v in STATE.current_polygon_vertices]
    msg = STATE.undo_edit()
    print(msg)
    return time.time(), no_update


# ── Room type buttons ─────────────────────────────────────────────────────────

_ROOM_TYPE_MAP = [
    ("rt-bed",     "BED"),
    ("rt-living",  "LIVING"),
    ("rt-nonresi", "NON-RESI"),
    ("rt-circ",    "CIRC"),
]

_TYPE_BTN_BASE = {
    "fontFamily": FONT_MONO, "fontSize": "10px", "padding": "3px 7px",
    "marginRight": "3px", "marginBottom": "3px", "borderRadius": "3px",
}


def _type_btn_style(active: bool) -> dict:
    s = dict(_TYPE_BTN_BASE)
    if active:
        s.update({"backgroundColor": C["btn_on"], "border": f"1px solid {C['accent']}", "color": C["accent"]})
    else:
        s.update({"backgroundColor": C["deep"], "border": f"1px solid {C['panel_bdr']}", "color": C["text_sec"]})
    return s


for _rt_id, _rt_val in _ROOM_TYPE_MAP:
    @app.callback(
        Output(_rt_id, "style"),
        Output("store-trigger", "data", allow_duplicate=True),
        Input(_rt_id, "n_clicks"),
        prevent_initial_call=True,
    )
    def _on_room_type(_, _val=_rt_val, _id=_rt_id):
        if STATE is not None:
            # Apply to all multi-selected rooms, or fall back to single selection
            targets = list(STATE.multi_selected_room_idxs) or (
                [STATE.selected_room_idx] if STATE.selected_room_idx is not None else []
            )
            for idx in targets:
                if 0 <= idx < len(STATE.rooms):
                    STATE.set_room_type(idx, _val)
        return _type_btn_style(True), time.time()

    # Keep other type buttons visually deselected when this one is active
    for _other_id, _other_val in _ROOM_TYPE_MAP:
        if _other_id != _rt_id:
            @app.callback(
                Output(_other_id, "style", allow_duplicate=True),
                Input(_rt_id, "n_clicks"),
                prevent_initial_call=True,
            )
            def _deselect_other(_, _oid=_other_id):
                return _type_btn_style(False)


# Sync all four type button styles when selected room changes
@app.callback(
    Output("rt-bed",     "style", allow_duplicate=True),
    Output("rt-living",  "style", allow_duplicate=True),
    Output("rt-nonresi", "style", allow_duplicate=True),
    Output("rt-circ",    "style", allow_duplicate=True),
    Input("store-trigger", "data"),
    prevent_initial_call=True,
)
def sync_type_btn_styles(_):
    if STATE is None or STATE.selected_room_idx is None:
        return (_type_btn_style(False),) * 4
    room = STATE.rooms[STATE.selected_room_idx] if STATE.selected_room_idx < len(STATE.rooms) else {}
    rtype = room.get("room_type", "")
    return tuple(_type_btn_style(rtype == val) for _, val in _ROOM_TYPE_MAP)


# ── Parent apartment selector ─────────────────────────────────────────────────

@app.callback(
    Output("input-parent", "value", allow_duplicate=True),
    Output("store-trigger", "data", allow_duplicate=True),
    Input("parent-prev", "n_clicks"),
    Input("parent-next", "n_clicks"),
    State("input-parent", "value"),
    prevent_initial_call=True,
)
def cycle_parent(prev_clicks, next_clicks, current_val):
    if STATE is None:
        return no_update, no_update
    opts = ["(None)"] + list(STATE.parent_options)
    if not opts:
        return no_update, no_update
    try:
        idx = opts.index(current_val) if current_val in opts else 0
    except ValueError:
        idx = 0
    triggered = ctx.triggered_id
    if triggered == "parent-prev":
        idx = (idx - 1) % len(opts)
    else:
        idx = (idx + 1) % len(opts)
    new_val = opts[idx]
    STATE.selected_parent = None if new_val == "(None)" else new_val
    return new_val, time.time()


# ── Sync parent input when a room is selected ─────────────────────────────────

@app.callback(
    Output("input-parent", "value", allow_duplicate=True),
    Output("input-room-name", "value"),
    Input("store-trigger", "data"),
    prevent_initial_call=True,
)
def sync_inputs_from_selection(_):
    if STATE is None:
        return no_update, no_update
    parent_val = STATE.selected_parent or "(None)"
    if STATE.selected_room_idx is not None and 0 <= STATE.selected_room_idx < len(STATE.rooms):
        room = STATE.rooms[STATE.selected_room_idx]
        room_name = room.get("name", "")
        # Strip the parent prefix for display in the input
        if STATE.selected_parent and room_name.startswith(STATE.selected_parent + "_"):
            room_name = room_name[len(STATE.selected_parent) + 1:]
        return parent_val, room_name
    return parent_val, no_update


# ── Tree row clicks ───────────────────────────────────────────────────────────

@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Input({"type": "tree-row", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def on_tree_click(n_clicks_list):
    if STATE is None:
        return no_update
    triggered = ctx.triggered_id
    if triggered is None:
        return no_update
    idx = triggered.get("index") if isinstance(triggered, dict) else None
    if isinstance(idx, int):
        STATE.selected_room_idx = idx
        room = STATE.rooms[idx]
        STATE.selected_parent = room.get("parent")
    elif isinstance(idx, str) and idx.startswith("node-"):
        node_key_str = idx[5:]
        try:
            node_key = eval(node_key_str)
            if node_key in STATE._tree_collapsed:
                STATE._tree_collapsed.discard(node_key)
            else:
                STATE._tree_collapsed.add(node_key)
        except Exception:
            pass
    return time.time()


# ── Tree expand / collapse all ────────────────────────────────────────────────

@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Input("tree-expand-all", "n_clicks"),
    Input("tree-collapse-all", "n_clicks"),
    prevent_initial_call=True,
)
def tree_expand_collapse(_, __):
    if STATE is None:
        return no_update
    triggered = ctx.triggered_id
    if triggered == "tree-expand-all":
        STATE._tree_collapsed.clear()
    else:
        # Collapse all HDR-level nodes
        items = STATE.build_layer_tree()
        for item in items:
            if item.get("has_children") and item.get("node_key"):
                try:
                    STATE._tree_collapsed.add(eval(item["node_key"]))
                except Exception:
                    pass
    return time.time()


# ── PDF overlay toggle ────────────────────────────────────────────────────────

@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Input("sb-overlay-toggle", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_overlay(_):
    if STATE is None:
        return no_update
    STATE._overlay_visible = not STATE._overlay_visible
    STATE._save_session()
    return time.time()


# ── PDF overlay page cycle ────────────────────────────────────────────────────

@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Input("sb-overlay-page", "n_clicks"),
    prevent_initial_call=True,
)
def cycle_overlay_page(_):
    if STATE is None:
        return no_update
    n = STATE.get_overlay_page_count()
    if n > 1:
        STATE._overlay_page_idx = (STATE._overlay_page_idx + 1) % n
        # Clear b64 cache for old page so the new page is freshly rasterized
        STATE._overlay_b64_cache.clear()
        STATE._save_session()
    return time.time()


# ── PDF DPI radio ─────────────────────────────────────────────────────────────

@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Input("pdf-dpi-radio", "value"),
    prevent_initial_call=True,
)
def change_overlay_dpi(dpi):
    if STATE is None or dpi is None:
        return no_update
    STATE._overlay_raster_dpi = int(dpi)
    STATE._overlay_b64_cache.clear()
    STATE._save_session()
    return time.time()


# ── Reset level alignment ─────────────────────────────────────────────────────

@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Output("overlay-offset-x", "value"),
    Output("overlay-offset-y", "value"),
    Output("overlay-scale-x", "value"),
    Output("overlay-scale-y", "value"),
    Input("btn-reset-align", "n_clicks"),
    prevent_initial_call=True,
)
def reset_overlay_align(_):
    if STATE is None:
        return no_update, 0, 0, 1.0, 1.0
    hdr_name = STATE.current_hdr_name or ""
    STATE._overlay_transforms.pop(hdr_name, None)
    STATE._save_session()
    return time.time(), 0, 0, 1.0, 1.0


# ── Overlay align mode toggle ─────────────────────────────────────────────────

@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Output("overlay-align-panel", "style"),
    Output("overlay-offset-x", "value", allow_duplicate=True),
    Output("overlay-offset-y", "value", allow_duplicate=True),
    Output("overlay-scale-x", "value", allow_duplicate=True),
    Output("overlay-scale-y", "value", allow_duplicate=True),
    Output("overlay-alpha", "value"),
    Input("sb-overlay-align", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_overlay_align(_):
    _PANEL_HIDDEN = {
        "display": "none",
        "position": "absolute", "top": "12px", "right": "12px",
        "backgroundColor": C["header"],
        "border": f"1px solid {C['panel_bdr']}",
        "borderRadius": "6px",
        "padding": "10px 12px",
        "boxShadow": "0 4px 16px rgba(0,0,0,0.12)",
        "zIndex": 30,
        "pointerEvents": "auto",
    }
    _PANEL_VISIBLE = dict(_PANEL_HIDDEN, display="block")

    if STATE is None:
        return no_update, _PANEL_HIDDEN, 0, 0, 1.0, 1.0, 0.6

    STATE.overlay_align_mode = not STATE.overlay_align_mode
    tf = STATE.get_overlay_transform()
    panel_style = _PANEL_VISIBLE if STATE.overlay_align_mode else _PANEL_HIDDEN
    return (
        time.time(),
        panel_style,
        tf.get("offset_x", 0.0),
        tf.get("offset_y", 0.0),
        tf.get("scale_x", 1.0),
        tf.get("scale_y", 1.0),
        STATE._overlay_alpha,
    )


# ── Overlay alignment inputs → update transform ───────────────────────────────

@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Input("overlay-offset-x", "value"),
    Input("overlay-offset-y", "value"),
    Input("overlay-scale-x", "value"),
    Input("overlay-scale-y", "value"),
    Input("overlay-alpha",   "value"),
    prevent_initial_call=True,
)
def update_overlay_transform(ox, oy, sx, sy, alpha):
    if STATE is None:
        return no_update
    if not STATE.overlay_align_mode:
        return no_update
    if None in (ox, oy, sx, sy):
        return no_update
    sx = max(0.01, float(sx))
    sy = max(0.01, float(sy))
    STATE.set_overlay_transform(float(ox), float(oy), sx, sy)
    if alpha is not None:
        STATE._overlay_alpha = max(0.0, min(1.0, float(alpha)))
        STATE._save_session()
    return time.time()


# ── DF% placement mode toggle ─────────────────────────────────────────────────

@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Input("sb-placement", "n_clicks"),
    Input("tool-dfplace", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_placement(_, __):
    if STATE is None:
        return no_update
    STATE.placement_mode = not STATE.placement_mode
    if STATE.placement_mode:
        # Start loading DF image in background so it's ready when user clicks
        # threading imported at top
        threading.Thread(target=STATE.load_df_image, daemon=True).start()
    return time.time()




# ── Export ────────────────────────────────────────────────────────────────────

_export_progress: dict = {"phase": "idle", "message": "", "pct": 0}


@app.callback(
    Output("export-poll", "disabled", allow_duplicate=True),
    Output("progress-bar-wrap", "style"),
    Input("sb-export", "n_clicks"),
    prevent_initial_call=True,
)
def start_export(_):
    if STATE is None:
        return True, {"display": "none"}
    # threading imported at top
    _export_progress.update({"phase": "starting", "message": "Starting export…", "pct": 0})
    threading.Thread(target=STATE.run_export, args=(_export_progress,), daemon=True).start()
    bar_style = {
        "height": "18px",
        "backgroundColor": C["deep"],
        "borderTop": f"1px solid {C['panel_bdr']}",
        "position": "relative",
        "flexShrink": "0",
        "display": "flex",
        "alignItems": "center",
    }
    return False, bar_style  # enable polling, show bar


@app.callback(
    Output("progress-fill", "style"),
    Output("progress-text", "children"),
    Output("export-poll", "disabled", allow_duplicate=True),
    Input("export-poll", "n_intervals"),
    prevent_initial_call=True,
)
def poll_export_progress(_):
    pct = _export_progress.get("pct", 0)
    msg = _export_progress.get("message", "")
    phase = _export_progress.get("phase", "idle")
    fill_style = {
        "height": "100%",
        "width": f"{pct}%",
        "backgroundColor": C["accent"] if phase != "error" else C["danger"],
        "borderRadius": "3px",
        "transition": "width 0.3s ease",
    }
    done = phase in ("done", "error", "idle")
    return fill_style, msg, done  # disable polling when finished


# ── AOI level cycling ─────────────────────────────────────────────────────────

@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Input("tree-aoi-level", "n_clicks"),
    Input("btn-aoi-level-bottom", "n_clicks"),
    prevent_initial_call=True,
)
def change_aoi_level(_, __):
    if STATE is None:
        return no_update
    msg = STATE.cycle_aoi_level()
    print(msg)
    return time.time()


# ── Fit to selected room ──────────────────────────────────────────────────────

@app.callback(
    Output("viewport-graph", "figure", allow_duplicate=True),
    Input("btn-fit", "n_clicks"),
    State("store-grid-spacing", "data"),
    State("store-grid-visible", "data"),
    prevent_initial_call=True,
)
def fit_to_room(_, grid_spacing, grid_visible):
    if STATE is None or STATE.selected_room_idx is None:
        return no_update
    if STATE.selected_room_idx >= len(STATE.rooms):
        return no_update
    verts = STATE.rooms[STATE.selected_room_idx]["vertices"]
    if not verts:
        return no_update
    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    pad_x = max(30, (max(xs) - min(xs)) * 0.15)
    pad_y = max(30, (max(ys) - min(ys)) * 0.15)
    fig = build_figure(
        grid_spacing=grid_spacing or 50,
        grid_visible=grid_visible if grid_visible is not None else True,
        state=STATE,
    )
    fig.update_layout(
        xaxis_range=[min(xs) - pad_x, max(xs) + pad_x],
        yaxis_range=[min(ys) - pad_y, max(ys) + pad_y],
    )
    return fig


# ── Select all rooms on current HDR ──────────────────────────────────────────

@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Input("btn-select-all", "n_clicks"),
    prevent_initial_call=True,
)
def select_all_rooms(_):
    if STATE is None:
        return no_update
    idxs = {i for i, r in enumerate(STATE.rooms) if STATE._is_room_on_current_hdr(r)}
    STATE.multi_selected_room_idxs = idxs
    return time.time()


# ── Zoom indicator ────────────────────────────────────────────────────────────

@app.callback(
    Output("zoom-indicator", "children"),
    Input("viewport-graph", "relayoutData"),
    prevent_initial_call=True,
)
def update_zoom_indicator(relay):
    if STATE is None or relay is None:
        return "100%"
    img_w, img_h = STATE.get_image_dimensions()
    if img_w == 0:
        return "100%"
    x_range = relay.get("xaxis.range[0]"), relay.get("xaxis.range[1]")
    if None in x_range:
        # autorange or reset
        return "100%"
    visible_w = abs(x_range[1] - x_range[0])
    pct = max(1, int(round(img_w / visible_w * 100)))
    return f"{pct}%"


# ── Project tree panel toggle (sb-menu) ──────────────────────────────────────

@app.callback(
    Output("project-tree-panel", "style"),
    Input("sb-menu", "n_clicks"),
    State("project-tree-panel", "style"),
    prevent_initial_call=True,
)
def toggle_project_tree(_, style):
    if style is None:
        style = {}
    if style.get("display") == "none":
        style = {
            "backgroundColor": C["panel_bg"],
            "borderRight": f"1px solid {C['panel_bdr']}",
            "display": "flex",
            "flexDirection": "column",
            "minWidth": "240px",
            "maxWidth": "300px",
            "height": "100%",
            "overflowY": "hidden",
        }
    else:
        style = dict(style, display="none")
    return style


# ── Floating palette: undo, zoom mode, pan mode ───────────────────────────────

@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Output("store-draw-vertices", "data", allow_duplicate=True),
    Input("tool-undo-fp", "n_clicks"),
    prevent_initial_call=True,
)
def undo_from_palette(_):
    if STATE is None:
        return no_update, no_update
    if STATE.draw_mode and STATE.current_polygon_vertices:
        STATE.current_polygon_vertices.pop()
        return time.time(), [[v[0], v[1]] for v in STATE.current_polygon_vertices]
    STATE.undo_edit()
    return time.time(), no_update


@app.callback(
    Output("viewport-graph", "config"),
    Input("tool-zoom", "n_clicks"),
    Input("tool-pan", "n_clicks"),
    State("viewport-graph", "config"),
    prevent_initial_call=True,
)
def set_drag_mode(zoom_clicks, pan_clicks, config):
    """Switch Plotly dragmode between zoom and pan via the floating palette."""
    triggered = ctx.triggered_id
    cfg = dict(config) if config else {}
    # Plotly config doesn't directly set dragmode; use figure update instead
    return no_update  # handled below via separate figure update

@app.callback(
    Output("viewport-graph", "figure", allow_duplicate=True),
    Input("tool-zoom", "n_clicks"),
    Input("tool-pan", "n_clicks"),
    State("store-grid-spacing", "data"),
    State("store-grid-visible", "data"),
    prevent_initial_call=True,
)
def set_dragmode_figure(zoom_clicks, pan_clicks, grid_spacing, grid_visible):
    triggered = ctx.triggered_id
    fig = build_figure(
        grid_spacing=grid_spacing or 50,
        grid_visible=grid_visible if grid_visible is not None else True,
        state=STATE,
    )
    dragmode = "zoom" if triggered == "tool-zoom" else "pan"
    fig.update_layout(dragmode=dragmode)
    return fig


# ── Extract archive modal ─────────────────────────────────────────────────────

@app.callback(
    Output("extract-modal", "is_open"),
    Output("extract-archive-select", "options"),
    Input("sb-extract", "n_clicks"),
    Input("btn-extract-cancel", "n_clicks"),
    State("extract-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_extract_modal(open_clicks, cancel_clicks, is_open):
    triggered = ctx.triggered_id
    if triggered == "sb-extract" and STATE is not None:
        archives = STATE.list_archives()
        options = [{"label": p.name, "value": str(p)} for p in archives]
        if not options:
            options = [{"label": "No archives found", "value": "", "disabled": True}]
        return True, options
    return False, []


@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Output("status-text", "children", allow_duplicate=True),
    Output("extract-modal", "is_open", allow_duplicate=True),
    Input("btn-extract-confirm", "n_clicks"),
    State("extract-archive-select", "value"),
    prevent_initial_call=True,
)
def confirm_extract(_, zip_path_str):
    if STATE is None or not zip_path_str:
        return no_update, "No archive selected.", False
    # Path imported at top
    msg = STATE.extract_and_reload(Path(zip_path_str))
    return time.time(), msg, False


# ── sb-history / sb-settings: placeholders ────────────────────────────────────

@app.callback(
    Output("status-text", "children", allow_duplicate=True),
    Input("sb-history", "n_clicks"),
    Input("sb-settings", "n_clicks"),
    prevent_initial_call=True,
)
def open_history_settings(_, __):
    triggered = ctx.triggered_id
    if triggered == "sb-history":
        return "History: not yet implemented"
    return "Settings: not yet implemented"


# ── Annotation scale slider ──────────────────────────────────────────────────

# Slider → state: user drags slider → update _annotation_scale → rebuild figure
@app.callback(
    Output("store-trigger", "data", allow_duplicate=True),
    Input("slider-annotation-scale", "value"),
    prevent_initial_call=True,
)
def annotation_scale_changed(slider_val):
    if STATE is not None and slider_val is not None:
        STATE._annotation_scale = float(slider_val)
        STATE._save_session()
    return time.time()


# State → slider: project load → push persisted value back to slider
@app.callback(
    Output("slider-annotation-scale", "value"),
    Input("store-trigger", "data"),
    prevent_initial_call=True,
)
def restore_annotation_scale(_):
    if STATE is not None:
        return STATE._annotation_scale
    return no_update


# ── Startup ───────────────────────────────────────────────────────────────────

_init_state()


if __name__ == "__main__":
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        webbrowser.open_new("http://127.0.0.1:8050/")
    app.run(debug=True)
