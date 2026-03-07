import dash
from dash import dcc, html, Input, Output, State, callback_context, no_update
import plotly.graph_objects as go
import cv2
import imageio.v2 as imageio
from PIL import Image
import numpy as np
import base64
import json
import os
import copy
from pathlib import Path

# Archilume imports
try:
    from archilume import config, utils
    from archilume.post.hdr2wpd import Hdr2Wpd
except ImportError:
    import sys
    sys.path.append(os.getcwd())
    from archilume import config, utils
    from archilume.post.hdr2wpd import Hdr2Wpd

# --- 1. Constants & Path Setup ---
IMAGE_DIR = Path(config.IMAGE_DIR)
SESSION_PATH = IMAGE_DIR / "aoi_session.json"
CSV_PATH = IMAGE_DIR / "aoi_boundaries.csv"
DF_THRESHOLDS = {'BED': 0.5, 'LIVING': 1.0, 'CIRC': None}

# Global Memory Caches
IMAGE_CACHE = {}
DF_CACHE = {}

# --- 2. Helper Functions ---
def parse_path(path_str):
    if not path_str or not isinstance(path_str, str): return []
    try:
        path_str = path_str.replace('M', '').replace('Z', '').strip()
        pts = path_str.split('L')
        return [[float(c) for c in pt.strip().split(',')] for pt in pts if pt.strip()]
    except Exception:
        return []

def format_path(pts):
    if not pts: return ""
    res = f"M {pts[0][0]},{pts[0][1]} "
    for p in pts[1:]:
        res += f"L {p[0]},{p[1]} "
    res += "Z"
    return res

def make_orthogonal(pts):
    if len(pts) < 3: return pts
    new_pts = [pts[0]]
    for i in range(1, len(pts)):
        prev = new_pts[-1]
        curr = pts[i]
        dx = abs(curr[0] - prev[0])
        dy = abs(curr[1] - prev[1])
        if dx > dy:
            new_pts.append([curr[0], prev[1]])
        else:
            new_pts.append([prev[0], curr[1]])
    return new_pts

def get_hdr_files():
    if not IMAGE_DIR.exists(): return []
    return sorted([f for f in IMAGE_DIR.glob("*.hdr")])

def get_variants_for_hdr(hdr_stem):
    variants = []
    # Add the base HDR
    base_hdr = IMAGE_DIR / f"{hdr_stem}.hdr"
    if base_hdr.exists():
        variants.append(base_hdr)
    # Add associated TIFFs
    tiffs = sorted([f for f in IMAGE_DIR.glob(f"{hdr_stem}_*.tiff") if not f.stem.endswith("_aoi_overlay")])
    variants.extend(tiffs)
    return variants

def load_and_tonemap(filepath):
    """Loads an image, tonemaps if HDR, returns base64 PNG and shape."""
    path = Path(filepath)
    key = str(path)
    if key in IMAGE_CACHE:
        return IMAGE_CACHE[key]
        
    if not path.exists():
        dummy = np.zeros((500, 500, 3), dtype=np.uint8)
        cv2.putText(dummy, "Image Not Found", (100, 250), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2)
        _, buffer = cv2.imencode('.png', dummy)
        res = f"data:image/png;base64,{base64.b64encode(buffer).decode('utf-8')}", dummy.shape
        return res

    if path.suffix.lower() == '.hdr':
        img = imageio.imread(str(path)).astype(np.float32)
        if img.ndim == 2:
            img = np.stack([img, img, img], axis=-1)
        p99 = np.percentile(img, 99)
        if p99 > 0:
            img = img / p99
        img = np.clip(img ** (1.0 / 2.2), 0.0, 1.0)
        img_rgb = (img * 255).astype(np.uint8)
    else:
        pil_img = Image.open(path).convert('RGB')
        img_rgb = np.array(pil_img)
    
    _, buffer = cv2.imencode('.png', cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR))
    b64_string = base64.b64encode(buffer).decode('utf-8')
    
    res = f"data:image/png;base64,{b64_string}", img_rgb.shape
    IMAGE_CACHE[key] = res
    return res

def load_df_array(hdr_stem):
    key = hdr_stem
    if key in DF_CACHE:
        return DF_CACHE[key]
    hdr_path = IMAGE_DIR / f"{hdr_stem}.hdr"
    if not hdr_path.exists():
        return None
    try:
        df_img = Hdr2Wpd.load_df_image(hdr_path)
        DF_CACHE[key] = df_img
        return df_img
    except Exception:
        return None

# --- 3. Data Persistence ---
def load_session():
    if SESSION_PATH.exists():
        try:
            with open(SESSION_PATH, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {}

def save_session(data):
    with open(SESSION_PATH, 'w') as f:
        json.dump(data, f, indent=4)

# --- 4. App Initialization & Layout ---
app = dash.Dash(__name__, title="Archilume AOI Editor")

# CSS Styles
styles = {
    'panel': {'padding': '15px', 'backgroundColor': '#f8f9fa', 'borderRight': '1px solid #dee2e6'},
    'header': {'padding': '15px 20px', 'backgroundColor': '#343a40', 'color': 'white', 'display': 'flex', 'justifyContent': 'space-between'},
    'label': {'fontWeight': 'bold', 'marginTop': '10px', 'display': 'block', 'fontSize': '14px', 'color': '#333'},
    'button': {'width': '100%', 'padding': '8px', 'marginTop': '10px', 'border': 'none', 'borderRadius': '4px', 'cursor': 'pointer', 'fontWeight': 'bold'},
    'btn-primary': {'backgroundColor': '#0d6efd', 'color': 'white'},
    'btn-success': {'backgroundColor': '#198754', 'color': 'white'},
    'btn-warning': {'backgroundColor': '#ffc107', 'color': 'black'},
    'btn-secondary': {'backgroundColor': '#6c757d', 'color': 'white'},
    'list-item': {'padding': '8px', 'borderBottom': '1px solid #ddd', 'cursor': 'pointer', 'fontSize': '13px'}
}

hdr_options = [{'label': f.stem, 'value': f.stem} for f in get_hdr_files()]

app.layout = html.Div([
    dcc.Store(id='session-store', data=load_session()),
    dcc.Store(id='undo-store', data=[]), 
    
    html.Div([
        html.Div([
            html.H3("Archilume Dash AOI Editor", style={'margin': '0'}),
            html.Small("Interactive Room Boundary Tool")
        ]),
        html.Div(id='top-status-bar', children="Ready", style={'color': '#17a2b8', 'fontWeight': 'bold', 'alignSelf': 'center'})
    ], style=styles['header']),

    html.Div([
        # Left Panel: Navigation & View
        html.Div([
            html.Label("1. Select HDR Floor Plan", style=styles['label']),
            dcc.Dropdown(id='hdr-selector', options=hdr_options, value=hdr_options[0]['value'] if hdr_options else None, clearable=False),
            
            html.Label("2. Image Layer Variant", style=styles['label']),
            dcc.Dropdown(id='variant-selector', clearable=False),
            
            html.Hr(),
            html.Label("Tools & Constraints", style=styles['label']),
            html.Button("Force Orthogonal Lines", id='btn-ortho', style={**styles['button'], **styles['btn-warning']}),
            html.Button("Undo Last Action", id='btn-undo', style={**styles['button'], **styles['btn-secondary']}),
            
            html.Hr(),
            html.Label("Cursor Readout", style=styles['label']),
            html.Div(id='df-readout', children="Hover over image for DF%", style={'padding': '10px', 'backgroundColor': '#212529', 'color': '#00ff00', 'fontFamily': 'monospace', 'textAlign': 'center', 'borderRadius': '4px'})
            
        ], style={**styles['panel'], 'width': '20%', 'minWidth': '250px'}),

        # Center Panel: Canvas
        html.Div([
            dcc.Graph(
                id='main-graph',
                config={
                    'modeBarButtonsToAdd': ['drawclosedpath', 'drawrect', 'eraseshape'],
                    'displayModeBar': True,
                    'scrollZoom': True
                },
                style={'height': '100%', 'width': '100%'}
            )
        ], style={'width': '60%', 'padding': '10px', 'backgroundColor': '#e9ecef', 'height': '100%'}),

        # Right Panel: Metadata & Rooms
        html.Div([
            html.Label("Selected Shape Properties", style=styles['label']),
            html.Div(id='selected-shape-id', style={'fontSize': '12px', 'color': 'gray', 'marginBottom': '5px'}),
            
            html.Label("Room Name"),
            dcc.Input(id='input-name', type='text', placeholder="e.g. U101_BED1", style={'width': '100%', 'padding': '5px', 'boxSizing': 'border-box'}),
            
            html.Label("Room Type"),
            dcc.Dropdown(
                id='input-type',
                options=[
                    {'label': 'BED (0.5% DF)', 'value': 'BED'},
                    {'label': 'LIVING (1.0% DF)', 'value': 'LIVING'},
                    {'label': 'CIRCULATION', 'value': 'CIRC'}
                ],
                value='BED'
            ),
            
            html.Label("Parent Apartment"),
            dcc.Dropdown(id='input-parent', placeholder="(None - New Apartment)"),
            
            html.Button("Update Shape Metadata", id='btn-update', n_clicks=0, style={**styles['button'], **styles['btn-primary']}),
            
            html.Hr(),
            html.Label("Saved Rooms (Current Floor)", style=styles['label']),
            html.Div(id='room-list-container', style={'overflowY': 'auto', 'maxHeight': '30vh', 'border': '1px solid #ccc', 'backgroundColor': 'white', 'borderRadius': '4px'}),
            
            html.Hr(),
            html.Button("Save All to Disk (JSON/CSV)", id='btn-save-disk', n_clicks=0, style={**styles['button'], **styles['btn-success']}),
            html.Div(id='save-feedback', style={'marginTop': '10px', 'textAlign': 'center'})
            
        ], style={**styles['panel'], 'width': '20%', 'minWidth': '250px'})
    ], style={'display': 'flex', 'height': 'calc(100vh - 60px)'})
], style={'fontFamily': 'sans-serif'})

# --- 5. Callbacks ---

@app.callback(
    Output('variant-selector', 'options'),
    Output('variant-selector', 'value'),
    Input('hdr-selector', 'value')
)
def update_variants(hdr_stem):
    if not hdr_stem: return [], None
    variants = get_variants_for_hdr(hdr_stem)
    options = [{'label': v.name, 'value': str(v)} for v in variants]
    return options, options[0]['value'] if options else None


@app.callback(
    Output('main-graph', 'figure'),
    Input('variant-selector', 'value'),
    Input('session-store', 'data'),
    State('hdr-selector', 'value')
)
def render_graph(variant_path, session_data, hdr_stem):
    if not variant_path or not hdr_stem: 
        return go.Figure()

    img_b64, img_shape = load_and_tonemap(variant_path)
    img_h, img_w, _ = img_shape
    
    fig = go.Figure()
    fig.add_layout_image(
        dict(
            source=img_b64,
            xref="x", yref="y",
            x=0, y=img_h,
            sizex=img_w, sizey=img_h,
            sizing="stretch",
            opacity=1,
            layer="below"
        )
    )
    
    shapes = []
    if hdr_stem in session_data:
        shapes = session_data[hdr_stem].get('shapes', [])
        
    fig.update_layout(
        xaxis=dict(visible=False, range=[0, img_w]),
        yaxis=dict(visible=False, range=[0, img_h], scaleanchor="x"),
        margin=dict(l=0, r=0, t=30, b=0),
        dragmode="drawclosedpath",
        newshape=dict(line_color="cyan", fillcolor="rgba(0, 255, 255, 0.2)", opacity=0.5, line_width=2),
        shapes=shapes,
        title=f"Editing: {Path(variant_path).name}"
    )
    
    if hdr_stem in session_data:
        meta = session_data[hdr_stem].get('metadata', {})
        for i, shape in enumerate(shapes):
            pts = parse_path(shape.get('path', ''))
            if pts:
                arr = np.array(pts)
                cx, cy = arr[:, 0].mean(), arr[:, 1].mean()
                name = meta.get(str(i), {}).get('name', '')
                if name:
                    fig.add_annotation(x=cx, y=cy, text=name, showarrow=False, font=dict(color='white', size=12, family="Arial Black"))

    return fig

@app.callback(
    Output('df-readout', 'children'),
    Input('main-graph', 'hoverData'),
    State('hdr-selector', 'value')
)
def update_hover_readout(hover_data, hdr_stem):
    if not hover_data or not hdr_stem:
        return "Hover over image for DF%"
    
    pt = hover_data['points'][0]
    x, y = int(pt['x']), int(pt['y'])
    
    df_img = load_df_array(hdr_stem)
    if df_img is not None:
        h, w = df_img.shape[:2]
        array_y = h - y - 1
        if 0 <= array_y < h and 0 <= x < w:
            val = df_img[array_y, x]
            return f"DF: {val:.2f}% @ ({x}, {array_y})"
            
    return f"Coord: ({x}, {y})"


@app.callback(
    [Output('session-store', 'data'),
     Output('undo-store', 'data'),
     Output('input-name', 'value'),
     Output('input-type', 'value'),
     Output('input-parent', 'value'),
     Output('input-parent', 'options'),
     Output('selected-shape-id', 'children')],
    [Input('main-graph', 'relayoutData'),
     Input('btn-update', 'n_clicks'),
     Input('btn-ortho', 'n_clicks'),
     Input('btn-undo', 'n_clicks')],
    [State('session-store', 'data'),
     State('undo-store', 'data'),
     State('hdr-selector', 'value'),
     State('input-name', 'value'),
     State('input-type', 'value'),
     State('input-parent', 'value')]
)
def handle_interactions(relayout_data, btn_update, btn_ortho, btn_undo, 
                        session_data, undo_store, hdr_stem, 
                        in_name, in_type, in_parent):
    ctx = callback_context
    if not ctx.triggered or not hdr_stem:
        return no_update, no_update, no_update, no_update, no_update, no_update, no_update
        
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if hdr_stem not in session_data:
        session_data[hdr_stem] = {'shapes': [], 'metadata': {}}
        
    current_shapes = session_data[hdr_stem].get('shapes', [])
    current_meta = session_data[hdr_stem].get('metadata', {})
    
    selected_idx = -1
    if current_shapes:
        selected_idx = len(current_shapes) - 1
        
    if trigger_id == 'btn-undo':
        if undo_store:
            prev_state = undo_store.pop()
            return prev_state, undo_store, no_update, no_update, no_update, no_update, "Restored previous state."
        return no_update, no_update, no_update, no_update, no_update, no_update, "Nothing to undo."

    state_backup = copy.deepcopy(session_data)

    if trigger_id == 'main-graph' and relayout_data:
        if 'shapes' in relayout_data:
            current_shapes = relayout_data['shapes']
        elif any(k.startswith('shapes[') for k in relayout_data.keys()):
            for key, val in relayout_data.items():
                if key.startswith('shapes['):
                    idx = int(key.split('[')[1].split(']')[0])
                    if idx < len(current_shapes):
                        if 'path' in key: current_shapes[idx]['path'] = val
                        if 'x0' in key: current_shapes[idx]['x0'] = val
                        if 'x1' in key: current_shapes[idx]['x1'] = val
                        if 'y0' in key: current_shapes[idx]['y0'] = val
                        if 'y1' in key: current_shapes[idx]['y1'] = val
                        selected_idx = idx

    elif trigger_id == 'btn-update':
        if selected_idx >= 0:
            current_meta[str(selected_idx)] = {
                'name': in_name,
                'type': in_type,
                'parent': in_parent
            }
            
    elif trigger_id == 'btn-ortho':
        if selected_idx >= 0 and current_shapes[selected_idx].get('type') == 'path':
            pts = parse_path(current_shapes[selected_idx]['path'])
            ortho_pts = make_orthogonal(pts)
            current_shapes[selected_idx]['path'] = format_path(ortho_pts)

    parent_opts = []
    for idx_str, m in current_meta.items():
        if not m.get('parent') and m.get('name'):
            parent_opts.append({'label': m['name'], 'value': m['name']})

    out_name = ""
    out_type = "BED"
    out_parent = None
    if selected_idx >= 0 and str(selected_idx) in current_meta:
        meta = current_meta[str(selected_idx)]
        out_name = meta.get('name', '')
        out_type = meta.get('type', 'BED')
        out_parent = meta.get('parent', None)

    session_data[hdr_stem]['shapes'] = current_shapes
    session_data[hdr_stem]['metadata'] = current_meta
    
    if json.dumps(state_backup) != json.dumps(session_data):
        undo_store.append(state_backup)
        if len(undo_store) > 10:
            undo_store.pop(0)

    sel_text = f"Editing Shape Index: {selected_idx}" if selected_idx >= 0 else "No shape selected."
    
    return session_data, undo_store, out_name, out_type, out_parent, parent_opts, sel_text

@app.callback(
    Output('room-list-container', 'children'),
    Input('session-store', 'data'),
    State('hdr-selector', 'value')
)
def update_room_list(session_data, hdr_stem):
    if not hdr_stem or hdr_stem not in session_data:
        return []
    
    meta = session_data[hdr_stem].get('metadata', {})
    items = []
    for idx, m in meta.items():
        name = m.get('name', f'Unnamed {idx}')
        items.append(html.Div(f"ID {idx}: {name} [{m.get('type', 'none')}]", style=styles['list-item']))
    
    return items

@app.callback(
    Output('save-feedback', 'children'),
    Input('btn-save-disk', 'n_clicks'),
    State('session-store', 'data')
)
def save_to_disk(n_clicks, session_data):
    if n_clicks == 0: return ""
    
    save_session(session_data)
    
    rows = []
    for filename, data in session_data.items():
        shapes = data.get('shapes', [])
        metadata = data.get('metadata', {})
        for i, shape in enumerate(shapes):
            meta = metadata.get(str(i), {})
            name = meta.get('name', f"Unnamed_{i}")
            parent = meta.get('parent', "")
            rtype = meta.get('type', "BED")
            
            verts = []
            if shape.get('type') == 'path':
                pts = parse_path(shape['path'])
                verts = [f"{p[0]},{p[1]}" for p in pts]
            
            rows.append(f"{filename},{name},{parent},{rtype},{' '.join(verts)}")
            
    with open(CSV_PATH, 'w') as f:
        f.write("filename,name,parent,type,vertices\n")
        f.write("\n".join(rows))
        
    return html.Span("Successfully Saved to Disk!", style={'color': '#198754', 'fontWeight': 'bold'})

if __name__ == '__main__':
    app.run(debug=True)
