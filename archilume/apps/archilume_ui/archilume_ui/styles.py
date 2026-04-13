"""Design tokens and shared styles from UI spec §2.

Surface/text/border tokens use rx.color_mode_cond(light, dark) so the
entire UI responds to Reflex's built-in color-mode toggle.

IMPORTANT: Tokens that are rx.Var (color_mode_cond results) cannot be
embedded in Python f-strings.  Use them only as direct prop values:
    color=COLORS["text_sec"]          ✓
    background=COLORS["panel_bg"]     ✓
    border=f"1px solid ..."           ✗  — use border_color= instead
"""

import reflex as rx

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _c(light: str, dark: str):
    """Return a rx.color_mode_cond expression."""
    return rx.color_mode_cond(light=light, dark=dark)


# ---------------------------------------------------------------------------
# Colour tokens
# ---------------------------------------------------------------------------

COLORS = {
    # Surfaces
    "sidebar":     _c("#f5f6f7", "#1a1d23"),
    "sidebar_act": _c("#e8eaed", "#2a2e38"),
    "header":      _c("#ffffff", "#1a1d23"),
    "panel_bg":    _c("#ffffff", "#1e2129"),
    "panel_bdr":   _c("#e2e5e9", "#2e333f"),
    "viewport":    _c("#f0f2f4", "#13151a"),
    "deep":        _c("#f0f2f4", "#252830"),
    "hover":       _c("#eef0f3", "#252830"),
    # Text
    "text_pri":    _c("#1a1f27", "#e8eaed"),
    "text_sec":    _c("#5a6472", "#8a95a3"),
    "text_dim":    _c("#9ba6b2", "#5a6472"),
    # Accents — identical in both modes
    "accent":           "#0d9488",
    "accent2":          "#4f6ef7",
    "btn_on":           _c("#ccfbf1", "#134e4a"),
    "btn_off":          "transparent",
    "danger":           "#dc2626",
    "warning":          "#d97706",
    "success":          "#059669",
    # Room polygon colours (SVG fill strings — static)
    "room_fill_selected":    "none",
    "room_fill_unselected":  "none",
    "room_stroke_selected":  "#facc15",
    "room_stroke_unselected":"#ef4444",
    "snap_highlight":   "#facc15",
    "df_stamp":         "#06b6d4",
    "divider_preview":  "#ec4899",
    "edit_vertex":      "#0d9488",
}

# Static border width string — combine with border_color prop separately
BORDER_1 = "1px solid"

# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------
FONT_HEAD = "'Space Grotesk', sans-serif"
FONT_MONO = "'JetBrains Mono', monospace"

GOOGLE_FONTS_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Space+Grotesk:wght@400;500;600;700&"
    "family=JetBrains+Mono:ital,wght@0,400;0,500;0,700;1,400&"
    "display=swap"
)

# ---------------------------------------------------------------------------
# Sizing constants
# ---------------------------------------------------------------------------
SIDEBAR_WIDTH = "52px"
PROJECT_TREE_WIDTH = "260px"
RIGHT_PANEL_WIDTH = "220px"
HEADER_HEIGHT = "46px"


# ---------------------------------------------------------------------------
# Reusable style fragments (static-only keys — no rx.Var here)
# ---------------------------------------------------------------------------

PANEL_CARD = {
    "border_radius": "6px",
    "margin_bottom": "8px",
    "overflow": "hidden",
}

PANEL_CARD_TITLE = {
    "font_family": FONT_MONO,
    "font_size": "10px",
    "text_transform": "uppercase",
    "letter_spacing": "0.08em",
    "padding": "6px 8px",
}

SECTION_LABEL = {
    "font_family": FONT_MONO,
    "font_size": "9px",
    "text_transform": "uppercase",
    "letter_spacing": "0.12em",
}

BODY_TEXT = {
    "font_family": FONT_MONO,
    "font_size": "13px",
}

KBD_BADGE = {
    "font_family": FONT_MONO,
    "font_size": "9px",
    "border_radius": "3px",
    "padding": "1px 4px",
}

SIDEBAR_DIVIDER = {
    "height": "1px",
    "opacity": "0.5",
    "margin": "0 8px",
}
