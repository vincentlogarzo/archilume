import os

import reflex as rx
from reflex.plugins import SitemapPlugin

config = rx.Config(
    app_name="archilume_app",
    api_url=os.environ.get("REFLEX_API_URL", os.environ.get("API_URL", "http://localhost:8000")),
    plugins=[SitemapPlugin()],
    tailwind={
        "theme": {
            "extend": {
                "colors": {
                    "sidebar": "#f5f6f7",
                    "sidebar-act": "#e8eaed",
                    "panel-bg": "#ffffff",
                    "panel-bdr": "#e2e5e9",
                    "viewport": "#f0f2f4",
                    "text-pri": "#1a1f27",
                    "text-sec": "#5a6472",
                    "text-dim": "#9ba6b2",
                    "accent": "#0d9488",
                    "accent2": "#4f6ef7",
                    "hover": "#eef0f3",
                    "btn-on": "#ccfbf1",
                    "deep": "#f0f2f4",
                    "danger": "#dc2626",
                    "warning": "#d97706",
                    "success": "#059669",
                },
                "fontFamily": {
                    "head": ["Syne", "sans-serif"],
                    "mono": ["DM Mono", "monospace"],
                },
            },
        },
    },
)
