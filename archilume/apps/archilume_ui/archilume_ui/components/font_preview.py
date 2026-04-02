"""Font preview page — visit /fonts to compare typeface options."""

import reflex as rx

_FONTS_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=DM+Mono:ital,wght@0,300;0,400;0,500;1,400&"
    "family=JetBrains+Mono:ital,wght@0,400;0,500;0,700;1,400&"
    "family=IBM+Plex+Mono:ital,wght@0,400;0,500;0,700;1,400&"
    "family=Space+Mono:ital,wght@0,400;0,700;1,400&"
    "family=Syne:wght@400;600;700&"
    "family=Space+Grotesk:wght@400;500;600;700&"
    "family=IBM+Plex+Sans:ital,wght@0,400;0,600;0,700;1,400&"
    "family=Geist:wght@400;500;600;700&"
    "display=swap"
)

_SAMPLE_HEADING = "Archilume HDR AOI Editor"
_SAMPLE_BODY = "Room L2000028 · BED · DF avg: 1.24% · Above 0.5%: 87%"
_SAMPLE_MONO = "S270P_plan_ffl_14300  TIFF  3 / 6  zoom: 100%"
_SAMPLE_CODE = "vertices: [[120.5, 340.2], [280.0, 340.2], [280.0, 480.0]]"

_BG = rx.color_mode_cond(light="#f8f9fa", dark="#13151a")
_CARD_BG = rx.color_mode_cond(light="#ffffff", dark="#1e2129")
_CARD_BDR = rx.color_mode_cond(light="#e2e5e9", dark="#2e333f")
_TEXT_PRI = rx.color_mode_cond(light="#1a1f27", dark="#e8eaed")
_TEXT_SEC = rx.color_mode_cond(light="#5a6472", dark="#8a95a3")
_TEXT_DIM = rx.color_mode_cond(light="#9ba6b2", dark="#5a6472")
_ACCENT = "#0d9488"


_FONTS = [
    {
        "label": "DM Mono  (current)",
        "heading_font": "'DM Mono', monospace",
        "body_font": "'DM Mono', monospace",
        "current": True,
    },
    {
        "label": "JetBrains Mono",
        "heading_font": "'JetBrains Mono', monospace",
        "body_font": "'JetBrains Mono', monospace",
        "current": False,
    },
    {
        "label": "IBM Plex Mono",
        "heading_font": "'IBM Plex Mono', monospace",
        "body_font": "'IBM Plex Mono', monospace",
        "current": False,
    },
    {
        "label": "Space Mono",
        "heading_font": "'Space Mono', monospace",
        "body_font": "'Space Mono', monospace",
        "current": False,
    },
    {
        "label": "Syne (heading) + DM Mono (body)  (current pair)",
        "heading_font": "Syne, sans-serif",
        "body_font": "'DM Mono', monospace",
        "current": True,
    },
    {
        "label": "Space Grotesk (heading) + JetBrains Mono (body)",
        "heading_font": "'Space Grotesk', sans-serif",
        "body_font": "'JetBrains Mono', monospace",
        "current": False,
    },
    {
        "label": "IBM Plex Sans (heading) + IBM Plex Mono (body)",
        "heading_font": "'IBM Plex Sans', sans-serif",
        "body_font": "'IBM Plex Mono', monospace",
        "current": False,
    },
    {
        "label": "Geist (heading) + JetBrains Mono (body)",
        "heading_font": "Geist, sans-serif",
        "body_font": "'JetBrains Mono', monospace",
        "current": False,
    },
]


def _font_card(info: dict) -> rx.Component:
    heading_font = info["heading_font"]
    body_font = info["body_font"]
    is_current = info["current"]

    return rx.box(
        # Card header
        rx.flex(
            rx.text(
                info["label"],
                style={"font_size": "11px", "font_weight": "600",
                       "font_family": "system-ui, sans-serif"},
                color=_ACCENT if is_current else _TEXT_SEC,
            ),
            rx.cond(
                is_current,
                rx.badge("current", style={"font_size": "9px", "margin_left": "8px"},
                         color=_ACCENT, background="#ccfbf1"),
                rx.fragment(),
            ),
            rx.spacer(),
            align="center",
            style={"padding": "8px 12px", "border_bottom": "1px solid"},
            border_color=_CARD_BDR,
        ),
        # Heading sample
        rx.text(
            _SAMPLE_HEADING,
            style={"font_family": heading_font, "font_size": "18px",
                   "font_weight": "700", "padding": "10px 12px 2px 12px",
                   "line_height": "1.3"},
            color=_TEXT_PRI,
        ),
        # Sub-heading
        rx.text(
            "HDR AOI Editor  ·  Daylight Factor Analysis",
            style={"font_family": heading_font, "font_size": "13px",
                   "font_weight": "400", "padding": "0 12px 8px 12px"},
            color=_TEXT_SEC,
        ),
        rx.box(style={"height": "1px", "margin": "0 12px"}, background=_CARD_BDR),
        # Body sample
        rx.text(
            _SAMPLE_BODY,
            style={"font_family": body_font, "font_size": "11px",
                   "padding": "8px 12px 2px 12px"},
            color=_TEXT_PRI,
        ),
        # Mono label sample
        rx.text(
            _SAMPLE_MONO,
            style={"font_family": body_font, "font_size": "11px",
                   "padding": "2px 12px"},
            color=_TEXT_SEC,
        ),
        # Code sample
        rx.text(
            _SAMPLE_CODE,
            style={"font_family": body_font, "font_size": "10px",
                   "padding": "2px 12px 10px 12px"},
            color=_TEXT_DIM,
        ),
        # Weight samples
        rx.flex(
            rx.text("Regular 400", style={"font_family": body_font,
                    "font_size": "11px", "font_weight": "400"}),
            rx.text("Medium 500", style={"font_family": body_font,
                    "font_size": "11px", "font_weight": "500"}),
            rx.text("Bold 700", style={"font_family": body_font,
                    "font_size": "11px", "font_weight": "700"}),
            rx.text("Italic", style={"font_family": body_font,
                    "font_size": "11px", "font_style": "italic"}),
            gap="16px", style={"padding": "4px 12px 10px 12px"},
            color=_TEXT_SEC,
        ),
        background=_CARD_BG,
        border="1px solid", border_color=_CARD_BDR,
        border_radius="8px",
        style={"overflow": "hidden"},
    )


def font_preview_page() -> rx.Component:
    return rx.box(
        rx.box(
            style={
                "position": "sticky", "top": "0", "z_index": "10",
                "padding": "12px 32px", "border_bottom": "1px solid",
            },
            background=_CARD_BG, border_color=_CARD_BDR,
        ),
        rx.flex(
            rx.text(
                "Font Preview",
                style={"font_size": "22px", "font_weight": "700",
                       "font_family": "system-ui, sans-serif",
                       "margin_bottom": "4px"},
                color=_TEXT_PRI,
            ),
            rx.text(
                "Compare typeface options for Archilume UI — heading & body pairs",
                style={"font_size": "13px", "font_family": "system-ui, sans-serif"},
                color=_TEXT_SEC,
            ),
            rx.spacer(),
            rx.color_mode.button(size="2", variant="ghost"),
            align="center",
            style={"padding": "20px 32px 16px 32px"},
        ),
        rx.box(
            *[_font_card(f) for f in _FONTS],
            style={
                "display": "grid",
                "grid_template_columns": "repeat(auto-fill, minmax(480px, 1fr))",
                "gap": "16px",
                "padding": "0 32px 32px 32px",
            },
        ),
        style={"min_height": "100vh"},
        background=_BG,
    )
