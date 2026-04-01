"""Design tokens and shared styles from UI spec §2."""

# ---------------------------------------------------------------------------
# Colour tokens
# ---------------------------------------------------------------------------
COLORS = {
    "sidebar": "#f5f6f7",
    "sidebar_act": "#e8eaed",
    "header": "#ffffff",
    "panel_bg": "#ffffff",
    "panel_bdr": "#e2e5e9",
    "viewport": "#f0f2f4",
    "text_pri": "#1a1f27",
    "text_sec": "#5a6472",
    "text_dim": "#9ba6b2",
    "accent": "#0d9488",
    "accent2": "#4f6ef7",
    "hover": "#eef0f3",
    "btn_on": "#ccfbf1",
    "btn_off": "transparent",
    "danger": "#dc2626",
    "warning": "#d97706",
    "success": "#059669",
    "deep": "#f0f2f4",
}

# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------
FONT_HEAD = "Syne, sans-serif"
FONT_MONO = "'DM Mono', monospace"

# Google Fonts import URL (inject into page <head>)
GOOGLE_FONTS_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=DM+Mono:wght@300;400;500&"
    "family=Syne:wght@400;600;700&"
    "display=swap"
)

# ---------------------------------------------------------------------------
# Sizing constants
# ---------------------------------------------------------------------------
SIDEBAR_WIDTH = "52px"
PROJECT_TREE_WIDTH = "260px"
RIGHT_PANEL_WIDTH = "220px"
HEADER_HEIGHT = "46px"
BOTTOM_ROW_HEIGHT = "160px"

# ---------------------------------------------------------------------------
# Reusable style fragments
# ---------------------------------------------------------------------------
PANEL_CARD = {
    "background": COLORS["panel_bg"],
    "border": f"1px solid {COLORS['panel_bdr']}",
    "border_radius": "6px",
    "margin_bottom": "8px",
    "overflow": "hidden",
}

PANEL_CARD_TITLE = {
    "font_family": FONT_MONO,
    "font_size": "10px",
    "text_transform": "uppercase",
    "letter_spacing": "0.08em",
    "color": COLORS["text_dim"],
    "padding": "6px 8px",
    "border_bottom": f"1px solid {COLORS['panel_bdr']}",
}

SECTION_LABEL = {
    "font_family": FONT_MONO,
    "font_size": "9px",
    "text_transform": "uppercase",
    "letter_spacing": "0.12em",
    "color": COLORS["text_dim"],
}

BODY_TEXT = {
    "font_family": FONT_MONO,
    "font_size": "11px",
    "color": COLORS["text_pri"],
}

KBD_BADGE = {
    "font_family": FONT_MONO,
    "font_size": "9px",
    "background": COLORS["deep"],
    "border": f"1px solid {COLORS['panel_bdr']}",
    "border_radius": "3px",
    "padding": "1px 4px",
}

SIDEBAR_DIVIDER = {
    "height": "1px",
    "background": COLORS["panel_bdr"],
    "opacity": "0.5",
    "margin": "6px 8px",
}
