
# archilume/archilume/apps/dash_app.py
#
# Bare-bones Dash UI — mirrors the full feature-set of hdr_aoi_editor_matplotlib.py.
# All buttons, panels, and tree structure from the matplotlib editor are reproduced here
# as static layout. Callbacks are stubs only.
#
# Run:  python -m archilume.apps.dash_app
#       http://127.0.0.1:8050/
#

import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State
from dash_iconify import DashIconify

app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Syne:wght@400;600;700&display=swap"
    ],
    suppress_callback_exceptions=True,
)

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
    sb_btn("lucide:folder-open",   "sb-project",       "Open / Create Project"),
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

    html.Div([
        # Root: HDR file
        _tree_row("level_01_north.hdr", "lucide:file-image", depth=0, expanded=True,
                  eye=False, cog=False),

        # Layer 1
        _tree_row("Layer 1 – False Colour",  "lucide:image",       depth=1, expanded=False,
                  eye=True, cog=False),
        # Layer 2
        _tree_row("Layer 2 – Contour Lines", "lucide:image",       depth=1, expanded=False,
                  eye=True, cog=False),
        # Layer 3 – PDF overlay (dimmed = not loaded)
        _tree_row("Layer 3 – PDF Floor Plan","lucide:file-text",   depth=1, expanded=False,
                  eye=True, cog=True, dimmed=True),
        # Layer 4 – Room Boundaries (highlighted)
        _tree_row("Layer 4 – Room Boundaries","lucide:vector-square", depth=1, expanded=True,
                  highlight=True, eye=False, cog=False),

        # Accent bar + room children
        html.Div([
            html.Div(style={
                "width": "2px", "backgroundColor": C["accent"],
                "borderRadius": "1px", "marginLeft": "30px",
                "marginRight": "5px", "flexShrink": "0",
            }),
            html.Div([
                # Apartment U101
                _tree_row("U101", "lucide:home", depth=0, expanded=True,
                          badge="BED", highlight=True),
                _tree_row("U101_BED1", "lucide:bed-double", depth=1, expanded=None,
                          badge="BED"),
                _tree_row("U101_LIV1", "lucide:sofa",       depth=1, expanded=None,
                          badge="LIVING"),
                _tree_row("U101_CIRC1","lucide:move",        depth=1, expanded=None,
                          badge="CIRC"),
                # Apartment U102
                _tree_row("U102", "lucide:home", depth=0, expanded=False,
                          badge="LIVING"),
                # Apartment U103 collapsed
                _tree_row("U103", "lucide:home", depth=0, expanded=False,
                          badge="BED", dimmed=True),
            ], style={"flexGrow": "1"}),
        ], style={"display": "flex", "marginTop": "2px", "marginBottom": "4px"}),

    ], style={"padding": "0 4px", "overflowY": "auto", "flexGrow": "1"}),

    # AOI level indicator at bottom of tree
    html.Div([
        DashIconify(icon="lucide:layers-2", width=12, color=C["text_dim"],
                    style={"marginRight": "5px"}),
        html.Span("AOI Level: 1 / 3", style={
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

], style={
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

        # Dot-grid background (placeholder; replace with dcc.Graph / plotly figure)
        html.Div(id="canvas-area", style={
            "flexGrow": "1",
            "backgroundImage": "radial-gradient(circle, #c4cad1 1px, transparent 1px)",
            "backgroundSize": "24px 24px",
        }),

        # Floating drawing tool palette (bottom-centre)
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
        }),

        # Zoom indicator (bottom-right)
        html.Div("100%", id="zoom-indicator", style={
            "position": "absolute", "bottom": "12px", "right": "12px",
            "fontSize": "10px", "fontFamily": FONT_MONO, "color": C["text_dim"],
            "backgroundColor": C["header"], "border": f"1px solid {C['panel_bdr']}",
            "borderRadius": "4px", "padding": "2px 6px",
            "zIndex": 10,
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
                 ("↑ / ↓",      "Navigate HDR files"),
                 ("T",          "Toggle image variant (HDR/TIFF)"),
                 ("D",          "Toggle draw mode"),
                 ("DD",         "Enter room divider mode"),
                 ("E",          "Toggle edit mode"),
                 ("O",          "Toggle ortho lines"),
                 ("P",          "Toggle DF% placement mode"),
                 ("S",          "Save room / confirm edit"),
                 ("F",          "Fit zoom to selected room"),
                 ("R",          "Reset zoom"),
                 ("Ctrl+Z",     "Undo (edit or draw mode)"),
                 ("Ctrl+A",     "Select all rooms on current HDR"),
                 ("Ctrl+Click", "Multi-select rooms in list"),
                 ("Esc",        "Exit mode / deselect"),
                 ("Q",          "Quit"),
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

], style={
    "display": "flex",
    "fontFamily": FONT_MONO,
    "backgroundColor": C["deep"],
    "color": C["text_pri"],
    "height": "100vh",
    "width": "100vw",
    "overflow": "hidden",
})

# ---------------------------------------------------------------- callbacks --
# All stubs — wire up real logic later.

@app.callback(
    Output("shortcuts-modal", "is_open"),
    Input("btn-shortcuts", "n_clicks"),
    Input("shortcuts-modal-close", "n_clicks"),
    State("shortcuts-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_shortcuts_modal(open_clicks, close_clicks, is_open):
    return not is_open


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


# Room type toggle stubs
for _btn_id in ("rt-bed", "rt-living", "rt-nonresi", "rt-circ"):
    @app.callback(
        Output(_btn_id, "style"),
        Input(_btn_id, "n_clicks"),
        prevent_initial_call=True,
    )
    def _toggle_room_type_btn(n, _id=_btn_id):
        # Real impl would track active state; stub just returns active style
        return {
            "fontFamily": FONT_MONO, "fontSize": "10px", "padding": "3px 7px",
            "backgroundColor": C["btn_on"], "border": f"1px solid {C['accent']}",
            "color": C["accent"], "marginRight": "3px", "marginBottom": "3px",
            "borderRadius": "3px",
        }


if __name__ == "__main__":
    import os, webbrowser
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        webbrowser.open_new("http://127.0.0.1:8050/")
    app.run(debug=True)
