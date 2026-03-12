


# archilume/archilume/apps/dash_app.py
import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State
from dash_iconify import DashIconify

app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Syne:wght@400;600;700&display=swap"
    ]
)

# --- Colour tokens ---
C = {
    "sidebar":    "#1a2332",
    "sidebar_act":"#243447",
    "header":     "#1e2d3d",
    "panel_bg":   "#1e2d3d",
    "panel_bdr":  "#2e4055",
    "viewport":   "#d4d8dd",
    "dot":        "#9aa5b1",
    "text_pri":   "#e8edf2",
    "text_sec":   "#7a909f",
    "text_dim":   "#4a6070",
    "accent":     "#4ec9b0",
    "accent2":    "#569cd6",
    "hover":      "#2a3f55",
}

FONT_HEAD = "Syne, sans-serif"
FONT_MONO = "'DM Mono', monospace"

# ------------------------------------------------------------------ helpers --

def sidebar_btn(icon, btn_id, tip, active=False):
    return html.Div([
        dbc.Button(
            DashIconify(icon=icon, width=22,
                        color=C["accent"] if active else C["text_sec"]),
            id=btn_id,
            color="link",
            style={
                "padding": "10px 0",
                "width": "52px",
                "display": "flex",
                "justifyContent": "center",
                "borderRadius": "8px",
                "backgroundColor": C["sidebar_act"] if active else "transparent",
                "border": "none",
                "transition": "background 0.15s",
            },
        ),
        dbc.Tooltip(tip, target=btn_id, placement="right"),
    ], style={"width": "52px", "marginBottom": "4px"})


def tree_item(label, icon, depth=0, expanded=False, has_eye=True, has_cog=True,
              highlight=False, children=None):
    indent = depth * 14
    row = html.Div([
        html.Div(
            DashIconify(
                icon="lucide:chevron-down" if expanded else "lucide:chevron-right",
                width=12, color=C["text_dim"]
            ) if children is not None else html.Div(style={"width": "12px"}),
            style={"marginRight": "4px", "flexShrink": "0"}
        ),
        DashIconify(icon=icon, width=14,
                    color=C["accent"] if highlight else C["text_sec"],
                    style={"marginRight": "6px", "flexShrink": "0"}),
        html.Span(label, style={
            "fontSize": "12px",
            "fontFamily": FONT_MONO,
            "color": C["text_pri"] if highlight else C["text_sec"],
            "fontWeight": "500" if highlight else "400",
            "flexGrow": "1",
            "whiteSpace": "nowrap",
            "overflow": "hidden",
            "textOverflow": "ellipsis",
        }),
        html.Div([
            DashIconify(icon="lucide:eye", width=13, color=C["text_dim"],
                        style={"cursor": "pointer", "marginLeft": "6px"}) if has_eye else None,
            DashIconify(icon="lucide:settings-2", width=13, color=C["text_dim"],
                        style={"cursor": "pointer", "marginLeft": "4px"}) if has_cog else None,
        ], style={"display": "flex", "alignItems": "center", "flexShrink": "0"}),
    ], style={
        "display": "flex",
        "alignItems": "center",
        "padding": f"4px 8px 4px {8 + indent}px",
        "borderRadius": "4px",
        "backgroundColor": C["hover"] if highlight else "transparent",
        "cursor": "pointer",
        "marginBottom": "1px",
    })
    nodes = [row]
    if children and expanded:
        nodes += children
    return html.Div(nodes)


def section_header(title):
    return html.Div(title, style={
        "fontSize": "10px",
        "fontFamily": FONT_MONO,
        "fontWeight": "500",
        "letterSpacing": "0.12em",
        "color": C["text_dim"],
        "textTransform": "uppercase",
        "padding": "10px 12px 4px",
    })


def panel_card(title, children):
    return html.Div([
        html.Div(title, style={
            "fontSize": "11px",
            "fontFamily": FONT_MONO,
            "color": C["text_sec"],
            "fontWeight": "500",
            "letterSpacing": "0.06em",
            "padding": "8px 12px 6px",
            "borderBottom": f"1px solid {C['panel_bdr']}",
        }),
        html.Div(children, style={"padding": "10px 12px"}),
    ], style={
        "backgroundColor": C["panel_bg"],
        "border": f"1px solid {C['panel_bdr']}",
        "borderRadius": "6px",
    })

# ------------------------------------------------------------------ sidebar --

sidebar = html.Div([
    # Menu
    sidebar_btn("lucide:menu", "btn-menu", "Menu"),
    html.Div(style={"height": "16px"}),

    # File ops
    sidebar_btn("lucide:folder-open", "btn-folder", "Open Project"),
    sidebar_btn("lucide:plus-circle", "btn-add", "New"),
    html.Div(style={"height": "16px"}),

    # Validate / undo / view
    sidebar_btn("lucide:check-circle-2", "btn-check", "Validate"),
    sidebar_btn("lucide:rotate-ccw", "btn-undo", "Undo"),
    sidebar_btn("lucide:eye", "btn-view", "View"),
    html.Div(style={"flex": "1"}),

    # Layers active
    sidebar_btn("lucide:layers", "btn-layers", "Layers", active=True),
    html.Div(style={"height": "24px"}),

    # History / settings at bottom
    sidebar_btn("lucide:clock-3", "btn-history", "History"),
    sidebar_btn("lucide:settings-2", "btn-settings", "Settings"),
], style={
    "width": "56px",
    "height": "100vh",
    "backgroundColor": C["sidebar"],
    "display": "flex",
    "flexDirection": "column",
    "alignItems": "center",
    "padding": "12px 0",
    "position": "fixed",
    "top": 0,
    "left": 0,
    "zIndex": 1000,
    "borderRight": f"1px solid {C['panel_bdr']}",
})

# ------------------------------------------------------------ project browser --

# Room boundary children
room_children = [
    tree_item("Parent : BED", "lucide:home", depth=4, has_eye=True, has_cog=True, highlight=True),
    tree_item("child : Living", "lucide:sofa", depth=5, has_eye=True, has_cog=True),
    tree_item("child : circ.", "lucide:move", depth=5, has_eye=True, has_cog=True),
]

# Layer 4 children
layer4_children = room_children

project_tree = html.Div([
    section_header("Project Browser"),

    tree_item("BuildingObjects", "lucide:building-2", depth=0, expanded=True, has_eye=False, has_cog=False,
              children=[html.Div()]),  # placeholder, rendered manually below

    # Manual tree since nesting is complex
    html.Div([
        # BuildingObjects
        html.Div([
            html.Div([
                DashIconify(icon="lucide:chevron-down", width=12, color=C["text_dim"],
                            style={"marginRight": "4px"}),
                DashIconify(icon="lucide:building-2", width=14, color=C["text_sec"],
                            style={"marginRight": "6px"}),
                html.Span("BuildingObjects", style={"fontSize": "12px", "fontFamily": FONT_MONO,
                                                     "color": C["text_sec"]}),
            ], style={"display": "flex", "alignItems": "center", "padding": "3px 8px"}),

            # Building.act
            html.Div([
                html.Div([
                    html.Div(style={"width": "12px", "marginRight": "4px"}),
                    DashIconify(icon="lucide:chevron-down", width=12, color=C["text_dim"],
                                style={"marginRight": "4px"}),
                    DashIconify(icon="lucide:file-box", width=14, color=C["accent2"],
                                style={"marginRight": "6px"}),
                    html.Span("Building .act", style={"fontSize": "12px", "fontFamily": FONT_MONO,
                                                       "color": C["text_pri"]}),
                ], style={"display": "flex", "alignItems": "center", "padding": "3px 8px"}),

                # floor plate 1
                html.Div([
                    html.Div(style={"width": "26px", "marginRight": "4px"}),
                    DashIconify(icon="lucide:chevron-down", width=12, color=C["text_dim"],
                                style={"marginRight": "4px"}),
                    DashIconify(icon="lucide:layout-panel-top", width=14, color=C["text_sec"],
                                style={"marginRight": "6px"}),
                    html.Span("Floor Plate 1", style={"fontSize": "12px", "fontFamily": FONT_MONO,
                                                       "color": C["text_sec"]}),
                ], style={"display": "flex", "alignItems": "center", "padding": "3px 8px"}),

                # Layer items
                *[html.Div([
                    html.Div(style={"width": "40px", "marginRight": "4px"}),
                    DashIconify(icon="lucide:chevron-right", width=12, color=C["text_dim"],
                                style={"marginRight": "4px"}),
                    html.Span(lbl, style={"fontSize": "11px", "fontFamily": FONT_MONO,
                                          "color": clr, "flexGrow": "1"}),
                    DashIconify(icon="lucide:eye", width=12, color=clr,
                                style={"marginRight": "4px"}),
                    DashIconify(icon="lucide:settings-2", width=12, color=C["text_dim"]),
                ], style={"display": "flex", "alignItems": "center",
                          "padding": "3px 8px", "opacity": op})
                  for lbl, clr, op in [
                      ("Layer 1 - False Color", C["text_sec"], "1"),
                      ("Layer 2 - Contour dist.", C["text_sec"], "1"),
                      ("Layer 3 Part", C["text_dim"], "0.45"),
                  ]],

                # Layer 4 - highlighted
                html.Div([
                    html.Div(style={"width": "40px", "marginRight": "4px"}),
                    DashIconify(icon="lucide:chevron-down", width=12, color=C["accent"],
                                style={"marginRight": "4px"}),
                    html.Span("Layer 4 - Room Boundaries", style={
                        "fontSize": "11px", "fontFamily": FONT_MONO,
                        "color": C["accent"], "flexGrow": "1",
                    }),
                    DashIconify(icon="lucide:settings-2", width=12, color=C["text_dim"]),
                ], style={"display": "flex", "alignItems": "center",
                          "padding": "3px 8px", "backgroundColor": C["hover"],
                          "borderRadius": "4px"}),

                # Room boundary children with left accent border
                html.Div([
                    html.Div(style={
                        "width": "2px", "backgroundColor": C["accent"],
                        "borderRadius": "1px", "marginLeft": "54px",
                        "marginRight": "6px", "flexShrink": "0",
                    }),
                    html.Div([
                        *[html.Div([
                            html.Span(label, style={
                                "fontSize": "11px", "fontFamily": FONT_MONO,
                                "color": C["text_pri"] if i == 0 else C["text_sec"],
                                "flexGrow": "1",
                            }),
                            DashIconify(icon="lucide:eye", width=12, color=C["text_dim"],
                                        style={"marginRight": "4px"}),
                            DashIconify(icon="lucide:settings-2", width=12, color=C["text_dim"]),
                        ], style={
                            "display": "flex", "alignItems": "center",
                            "padding": "3px 8px",
                            "backgroundColor": C["hover"] if i == 0 else "transparent",
                            "borderRadius": "4px", "marginBottom": "1px",
                        }) for i, label in enumerate([
                            "Parent : BED",
                            "child : Living",
                            "child : circ.",
                        ])],
                    ], style={"flexGrow": "1"}),
                ], style={"display": "flex", "marginTop": "2px", "marginBottom": "4px"}),

            ]),
        ]),
    ], style={"padding": "0 4px"}),
], style={
    "backgroundColor": C["panel_bg"],
    "borderRight": f"1px solid {C['panel_bdr']}",
    "overflowY": "auto",
    "minWidth": "280px",
    "maxWidth": "350px",
    "height": "100%",
})

# --------------------------------------------------------- bottom panels -----

model_validation_panel = panel_card("Model Validation Panel", html.Div([
    html.Div([
        DashIconify(icon="lucide:zap", width=12, color=C["accent"],
                    style={"marginRight": "6px", "flexShrink": "0"}),
        html.Span("Accelerated RT Pict", style={
            "fontSize": "11px", "fontFamily": FONT_MONO, "color": C["text_sec"],
        }),
    ], style={"display": "flex", "alignItems": "center", "marginBottom": "6px"}),
    html.Div([
        DashIconify(icon="lucide:scan-search", width=12, color=C["text_dim"],
                    style={"marginRight": "6px", "flexShrink": "0"}),
        html.Span("Preview simulation boundary checks", style={
            "fontSize": "11px", "fontFamily": FONT_MONO, "color": C["text_sec"],
        }),
    ], style={"display": "flex", "alignItems": "center", "marginBottom": "6px"}),
    html.Div([
        DashIconify(icon="lucide:brush", width=12, color=C["text_dim"],
                    style={"marginRight": "6px", "flexShrink": "0"}),
        html.Span("Cleaning tools", style={
            "fontSize": "11px", "fontFamily": FONT_MONO, "color": C["text_sec"],
        }),
    ], style={"display": "flex", "alignItems": "center", "marginBottom": "6px"}),
    html.Div([
        DashIconify(icon="lucide:info", width=12, color=C["accent2"],
                    style={"marginRight": "6px", "flexShrink": "0"}),
        html.Span("Note: Done here before Sun Merger", style={
            "fontSize": "10px", "fontFamily": FONT_MONO,
            "color": C["accent2"], "fontWeight": "500",
        }),
    ], style={"display": "flex", "alignItems": "flex-start",
              "backgroundColor": "#1a2c3d", "borderRadius": "4px",
              "padding": "6px 8px", "border": f"1px solid {C['accent2']}22"}),
]))

simulation_manager_panel = panel_card("Simulation Manager Panel", html.Div([
    html.Div([
        html.Span("Scenario grid:", style={
            "fontSize": "11px", "fontFamily": FONT_MONO,
            "color": C["text_sec"], "marginBottom": "4px", "display": "block",
        }),
        dbc.Select(
            options=[{"label": "Default", "value": "default"}],
            style={
                "fontSize": "11px", "fontFamily": FONT_MONO,
                "backgroundColor": "#141e2b", "color": C["text_sec"],
                "border": f"1px solid {C['panel_bdr']}",
                "borderRadius": "4px", "marginBottom": "8px",
            }
        ),
    ]),
    dbc.Button([
        DashIconify(icon="lucide:play-circle", width=13, style={"marginRight": "6px"}),
        "Review simulation"
    ], color="secondary", size="sm",
       style={"width": "100%", "fontFamily": FONT_MONO, "fontSize": "11px",
              "marginBottom": "6px", "backgroundColor": C["hover"],
              "border": f"1px solid {C['panel_bdr']}"}),
    dbc.Button([
        DashIconify(icon="lucide:cloud-upload", width=13, style={"marginRight": "6px"}),
        "Connect to cloud"
    ], color="secondary", size="sm",
       style={"width": "100%", "fontFamily": FONT_MONO, "fontSize": "11px",
              "marginBottom": "10px", "backgroundColor": C["hover"],
              "border": f"1px solid {C['panel_bdr']}"}),
    html.Div([
        html.Span("Compliance framework:", style={
            "fontSize": "11px", "fontFamily": FONT_MONO,
            "color": C["text_sec"], "marginBottom": "4px", "display": "block",
        }),
        html.Div([
            dbc.Select(
                options=[
                    {"label": "BESS", "value": "bess"},
                    {"label": "Green Star", "value": "greenstar"},
                    {"label": "NABERS", "value": "nabers"},
                    {"label": "EN 17037", "value": "en17037"},
                ],
                value="bess",
                style={
                    "fontSize": "11px", "fontFamily": FONT_MONO,
                    "backgroundColor": "#141e2b", "color": C["text_sec"],
                    "border": f"1px solid {C['panel_bdr']}",
                    "borderRadius": "4px 0 0 4px", "flexGrow": "1",
                }
            ),
            html.Div(
                DashIconify(icon="lucide:heart", width=14, color="#e05c7a"),
                style={
                    "padding": "6px 10px",
                    "backgroundColor": "#141e2b",
                    "border": f"1px solid {C['panel_bdr']}",
                    "borderLeft": "none",
                    "borderRadius": "0 4px 4px 0",
                    "cursor": "pointer",
                }
            ),
        ], style={"display": "flex"}),
    ]),
]))

# -------------------------------------------------------- viewport area ------

# Dotted-grid drafting canvas using radial-gradient
viewport = html.Div([
    # Toolbar strip at top of viewport
    html.Div([
        html.Div([
            DashIconify(icon="lucide:box-select", width=16, color=C["text_dim"],
                        style={"marginRight": "4px"}),
            DashIconify(icon="lucide:chevron-down", width=12, color=C["text_dim"],
                        style={"marginRight": "12px"}),
            DashIconify(icon="lucide:cloud", width=16, color=C["text_dim"]),
        ], style={
            "display": "flex", "alignItems": "center",
            "backgroundColor": C["panel_bg"],
            "border": f"1px solid {C['panel_bdr']}",
            "borderRadius": "6px", "padding": "5px 10px",
            "position": "absolute", "top": "12px", "left": "12px",
            "zIndex": 10,
        }),
        html.Div("MUTUALLY\nEXCLUSIVE", style={
            "position": "absolute", "right": "8px", "top": "50%",
            "transform": "translateY(-50%) rotate(90deg)",
            "fontSize": "9px", "fontFamily": FONT_MONO,
            "letterSpacing": "0.15em", "color": C["text_dim"],
            "whiteSpace": "pre", "textAlign": "center",
        }),
    ], style={"position": "relative", "height": "44px"}),

    # The canvas area
    html.Div(style={
        "flexGrow": "1",
        "backgroundImage": (
            "radial-gradient(circle, #8a9baa 1px, transparent 1px)"
        ),
        "backgroundSize": "24px 24px",
        "backgroundPosition": "0 0",
    }),

    # Floating tool palette (bottom-centre, like image 2)
    html.Div([
        *[html.Div([
            DashIconify(icon=ic, width=15, color=C["text_sec"],
                        style={"marginRight": "8px"}),
            html.Span(lbl, style={"fontSize": "11px", "fontFamily": FONT_MONO,
                                   "color": C["text_sec"]}),
        ], style={
            "display": "flex", "alignItems": "center",
            "padding": "5px 10px",
            "borderBottom": f"1px solid {C['panel_bdr']}" if lbl != "Divider" else "none",
            "cursor": "pointer",
        }) for ic, lbl in [
            ("lucide:git-commit-horizontal", "Vertex"),
            ("lucide:pen-tool", "Stamp/Path"),
            ("lucide:search", "Magnifying Glass"),
            ("lucide:mouse-pointer-2", "Edit Mode"),
            ("lucide:square", "Rectangle"),
            ("lucide:pentagon", "Polygon"),
            ("lucide:layout-panel-left", "Divider"),
        ]],
    ], style={
        "position": "absolute", "bottom": "16px", "left": "50%",
        "transform": "translateX(-50%)",
        "backgroundColor": C["header"],
        "border": f"1px solid {C['panel_bdr']}",
        "borderRadius": "8px",
        "boxShadow": "0 8px 24px rgba(0,0,0,0.4)",
        "zIndex": 20,
        "minWidth": "180px",
    }),

], style={
    "flexGrow": "1",
    "display": "flex",
    "flexDirection": "column",
    "position": "relative",
    "backgroundColor": C["viewport"],
    "overflow": "hidden",
})

# --------------------------------------------------------- bottom row --------

bottom_row = html.Div([
    html.Div(model_validation_panel, style={"width": "400px", "marginRight": "12px"}),
    html.Div(simulation_manager_panel, style={"flex": "1"}),
], style={
    "display": "flex",
    "padding": "12px 16px",
    "backgroundColor": "#17212e",
    "borderTop": f"1px solid {C['panel_bdr']}",
    "minHeight": "160px",
})

# -------------------------------------------------------- header --------------

header = html.Div([
    html.Span("Archilume", style={
        "fontFamily": FONT_HEAD,
        "fontWeight": "700",
        "fontSize": "18px",
        "color": C["text_pri"],
        "marginRight": "20px",
        "letterSpacing": "-0.02em",
    }),
    html.Div(style={
        "width": "1px", "height": "20px",
        "backgroundColor": C["panel_bdr"], "marginRight": "20px",
    }),
    html.Span("[Workflow Name]", style={
        "fontFamily": FONT_MONO, "fontSize": "12px",
        "color": C["text_sec"], "marginRight": "12px",
    }),
    html.Span("[Project Status]", style={
        "fontFamily": FONT_MONO, "fontSize": "11px",
        "color": C["text_dim"],
        "backgroundColor": "#141e2b",
        "padding": "2px 8px", "borderRadius": "3px",
        "border": f"1px solid {C['panel_bdr']}",
    }),
], style={
    "display": "flex",
    "alignItems": "center",
    "height": "48px",
    "backgroundColor": C["header"],
    "borderBottom": f"1px solid {C['panel_bdr']}",
    "paddingLeft": "16px",
})

# --------------------------------------------------------- full layout -------

app.layout = html.Div([
    # Sidebar (fixed)
    sidebar,

    # Everything to the right of sidebar
    html.Div([
        header,

        # Middle: viewport + right panel
        html.Div([
            project_tree,
            viewport,
        ], style={
            "display": "flex",
            "flex": "1",
            "overflow": "hidden",
        }),

        # Bottom panels
        bottom_row,

    ], style={
        "marginLeft": "56px",
        "display": "flex",
        "flexDirection": "column",
        "height": "100vh",
        "flex": "1", # Added flex: 1 to ensure it fills remaining width
        "overflow": "hidden",
    }),

], style={
    "display": "flex",
    "fontFamily": FONT_MONO,
    "backgroundColor": "#141e2b",
    "color": C["text_pri"],
    "height": "100vh",
    "width": "100vw", # Added width: 100vw to fill full browser width
    "overflow": "hidden",
})

if __name__ == "__main__":
    import os
    import webbrowser
    # Only open browser once (avoids double-opening when Dash reloader starts)
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        webbrowser.open_new("http://127.0.0.1:8050/")
    app.run(debug=True)