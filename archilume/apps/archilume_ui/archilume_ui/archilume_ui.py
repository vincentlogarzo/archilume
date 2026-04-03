"""Main page — composes all layout regions from spec §1."""

import reflex as rx

from .components.bottom_row import bottom_row
from .components.header import header
from .components.modals import (
    accelerad_modal,
    create_project_modal,
    extract_archive_modal,
    open_project_modal,
    shortcuts_modal,
)
from .components.font_preview import font_preview_page
from .components.project_tree import project_tree
from .components.sidebar import sidebar
from .components.viewport import viewport
from .state import EditorState
from .styles import COLORS, FONT_MONO, GOOGLE_FONTS_URL, SIDEBAR_WIDTH

_FONTS_PREVIEW_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=JetBrains+Mono:ital,wght@0,400;0,500;0,700;1,400&"
    "family=IBM+Plex+Mono:ital,wght@0,400;0,500;0,700;1,400&"
    "family=Space+Mono:ital,wght@0,400;0,700;1,400&"
    "family=Space+Grotesk:wght@400;500;600;700&"
    "family=IBM+Plex+Sans:ital,wght@0,400;0,600;0,700;1,400&"
    "family=Geist:wght@400;500;600;700&"
    "display=swap"
)


# Prevent browser pinch-zoom and page scroll-zoom; canvas handles its own wheel events
_ZOOM_GUARD_SCRIPT = rx.script("""
(function() {
    // Block Ctrl+wheel (pinch) everywhere — no pinch zoom anywhere in the app
    window.addEventListener('wheel', function(e) {
        if (e.ctrlKey) e.preventDefault();
    }, { passive: false });

    // Block pinch-zoom (gesturestart is Safari; touchmove with 2 fingers is cross-browser)
    window.addEventListener('gesturestart', function(e) { e.preventDefault(); }, { passive: false });
    window.addEventListener('gesturechange', function(e) { e.preventDefault(); }, { passive: false });
    window.addEventListener('touchmove', function(e) {
        if (e.touches.length > 1) e.preventDefault();
    }, { passive: false });
})();
""")


# Global keyboard handler — captures keys not handled by input elements
_KEYBOARD_SCRIPT = rx.script("""
(function() {
    function dispatch(event, payload) {
        if (typeof window.applyEvent === 'function') {
            window.applyEvent(event, payload);
        }
    }

    document.addEventListener('keydown', function(e) {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
        if (e.ctrlKey && e.key === 'z') { e.preventDefault(); dispatch('editor_state.undo', {}); return; }
        if (e.ctrlKey && e.key === 'a') { e.preventDefault(); dispatch('editor_state.select_all_rooms', {}); return; }
        if (e.ctrlKey && e.key === 'r') { e.preventDefault(); dispatch('editor_state.rotate_overlay_90', {}); return; }
        if (e.shiftKey && e.key === 'S') { e.preventDefault(); dispatch('editor_state.force_save', {}); return; }
        if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); dispatch('editor_state.delete_hovered_vertex', {}); return; }
        if (e.key.length === 1 || e.key === 'Escape' || e.key.startsWith('Arrow')) {
            e.preventDefault();
            if (document.activeElement && document.activeElement !== document.body) {
                document.activeElement.blur();
            }
            dispatch('editor_state.handle_key', {key: e.key});
        }
    });
})();
""")


def index() -> rx.Component:
    return rx.box(
        _ZOOM_GUARD_SCRIPT,
        _KEYBOARD_SCRIPT,
        _DEBUG_SCRIPT,
        sidebar(),
        rx.flex(
            header(),
            rx.flex(
                project_tree(),
                viewport(),
                style={"flex": "1", "overflow": "hidden"},
            ),
            bottom_row(),
            direction="column",
            style={
                "margin_left": SIDEBAR_WIDTH, "height": "100vh",
                "width": f"calc(100vw - {SIDEBAR_WIDTH})", "overflow": "hidden",
            },
        ),
        shortcuts_modal(),
        open_project_modal(),
        create_project_modal(),
        extract_archive_modal(),
        accelerad_modal(),
        style={
            "font_family": FONT_MONO, "font_size": "18px",
            "color": COLORS["text_pri"], "background": COLORS["viewport"],
        },
    )


_DEBUG_SCRIPT = rx.script("""
(function() {
    var panel = document.createElement('div');
    panel.id = 'dbg-panel';
    panel.style.cssText = [
        'position:fixed', 'bottom:8px', 'right:8px', 'z-index:9999',
        'background:rgba(0,0,0,0.82)', 'color:#0f0', 'font:11px/1.4 monospace',
        'padding:8px 10px', 'border-radius:6px', 'min-width:320px', 'max-width:420px',
        'max-height:200px', 'overflow-y:auto', 'pointer-events:none',
        'display:none',
    ].join(';');
    document.body.appendChild(panel);

    var visible = false;
    var lines = [];

    function log(msg) {
        var ts = new Date().toISOString().substr(11,8);
        lines.push('[' + ts + '] ' + msg);
        if (lines.length > 40) lines.shift();
        panel.innerHTML = lines.slice().reverse().map(function(l) {
            return '<div>' + l + '</div>';
        }).join('');
    }

    // Toggle with backtick key
    document.addEventListener('keydown', function(e) {
        if (e.key === '`') {
            visible = !visible;
            panel.style.display = visible ? 'block' : 'none';
        }
    }, true);

    // Patch applyEvent to log dispatches
    function patchApplyEvent() {
        if (!window.applyEvent) { setTimeout(patchApplyEvent, 300); return; }
        var orig = window.applyEvent;
        window.applyEvent = function(event, payload) {
            log('→ dispatch: ' + event + ' ' + JSON.stringify(payload).substr(0,60));
            return orig.apply(this, arguments);
        };
        log('applyEvent patched OK');
    }
    patchApplyEvent();

    // Log wheel events
    window.addEventListener('wheel', function(e) {
        var onCanvas = !!e.target.closest('#editor-svg');
        log('wheel dy=' + e.deltaY.toFixed(1) + ' ctrl=' + e.ctrlKey + ' canvas=' + onCanvas + ' prevented=' + e.defaultPrevented);
    }, { passive: true, capture: true });

    // Log pinch/gesture
    window.addEventListener('gesturechange', function(e) {
        log('gesture scale=' + (e.scale||'?').toFixed(3));
    }, { passive: true, capture: true });

    // Log key presses
    document.addEventListener('keydown', function(e) {
        if (e.key === '`') return;
        log('key=' + e.key + ' ctrl=' + e.ctrlKey + ' shift=' + e.shiftKey);
    }, { passive: true, capture: true });

    log('Debug overlay ready — press ` to toggle');
})();
""")


app = rx.App(
    style={"font_family": FONT_MONO, "font_size": "18px"},
    stylesheets=[GOOGLE_FONTS_URL, _FONTS_PREVIEW_URL],
)
app.add_page(index, on_load=EditorState.init_on_load, title="Archilume")
app.add_page(font_preview_page, route="/fonts", title="Archilume — Font Preview")
