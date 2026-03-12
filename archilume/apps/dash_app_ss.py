"""
seek icons at https://icon-sets.iconify.design/
ph:folder-open-light
ep:circle-plus
raphael:cloud2
ph:tree-view-light, clarity:tree-view-line, hugeicons:node-edit
mingcute:brush-3-ai-line
wpf:cut-paper
ph:polygon-light
gis:square-pt
pepicons-pencil:rewind-time-circle
lets-icons:setting-line-light
streamline:user-check-validate
mdi:floor-plan
fluent:tag-edit-28-regular
fa7-regular:edit
akar-icons:eye-open AND formkit:eyeclosed
material-symbols-light:print-outline
mdi:ray-vertex
fluent:save-28-regular
fluent:layer-20-regular
glyphs:filing-cabinet
boxicons:perpendicular-filled
streamline-plump:file-report
material-symbols-light:delete-outline
carbon:zoom-fit

"""

# archilume/archilume/apps/dash_app.py
import dash
import dash_bootstrap_components as dbc
from dash import html, dcc
from dash_iconify import DashIconify

# 1. Initialize the app with a Bootstrap theme
# We'll use FLATLY for a modern, clean look
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.FLATLY]
)

# Sidebar helper to create buttons with icons
def sidebar_btn(icon_name, btn_id, tooltip_text):
    return html.Div([
        dbc.Button(
            DashIconify(icon=icon_name, width=28, color="#ecf0f1"),
            id=btn_id,
            color="link",
            style={
                "padding": "12px 0",
                "width": "100%",
                "display": "flex",
                "justifyContent": "center",
                "border": "none"
            },
        ),
        dbc.Tooltip(tooltip_text, target=btn_id, placement="right"),
    ], style={"width": "100%"})

# 2. Define the layout
app.layout = html.Div([
    # Sidebar using Dash Bootstrap Components and Dash Iconify
    html.Div([
        # Menu Icon (top)
        sidebar_btn("lucide:menu", "menu-btn", "Expand Menu"),
        
        # Spacer
        html.Div(style={"flex": "0 0 20px"}),
        
        # Folder and Add icons
        sidebar_btn("lucide:folder", "folder-btn", "Open Project"),
        sidebar_btn("lucide:plus-circle", "add-btn", "New Project"),
        
    ], style={
        "width": "64px",
        "height": "100vh",
        "backgroundColor": "#fa9f48", # Dark Slate
        "display": "flex",
        "flexDirection": "column",
        "alignItems": "center",
        "position": "fixed",
        "top": 0,
        "left": 0,
        "zIndex": 1000,
    }),

    # Main Content Area
    html.Div([
        dbc.Container([
            html.H1("Archilume", className="mt-4 mb-2 text-primary"),
            html.P("Ready for simulation and analysis.", className="lead text-muted"),
            
            html.Hr(),
            
            # Content placeholder using Bootstrap Cards
            dbc.Card([
                dbc.CardBody([
                    html.H4("Project Workspace", className="card-title"),
                    html.P("Select a project or create a new one to begin."),
                    dbc.Button("Get Started", color="primary")
                ])
            ], className="mt-4 shadow-sm")
            
        ], fluid=True)
    ], style={
        "marginLeft": "64px", 
        "padding": "20px",
        "flexGrow": 1,
        "backgroundColor": "#f8f9fa",
        "minHeight": "100vh"
    })
], style={"display": "flex", "fontFamily": "Inter, sans-serif"})

# 3. Callbacks would go here
# @app.callback(...)

if __name__ == "__main__":
    app.run(debug=True)
