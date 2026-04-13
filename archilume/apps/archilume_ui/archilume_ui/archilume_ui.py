"""Main page — composes all layout regions from spec §1."""

import reflex as rx

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


# Prevent browser pinch-zoom and page scroll-zoom; canvas handles its own wheel events.
# Also blocks keydown propagation when an input/textarea/select is focused so that
# window_event_listener does not fire shortcuts while the user is typing.
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

    // Lightweight tracer: fires window.applyEvent('editor_state.log_js_trace', ...)
    // when the bridge is available. Silent no-op otherwise so it never throws.
    function _trace(tag, data) {
        try {
            if (window.applyEvent) {
                window.applyEvent('editor_state.log_js_trace',
                    { payload: Object.assign({ tag: tag, t: Date.now() }, data || {}) });
            }
        } catch (err) { /* swallow */ }
    }
    window._archilumeTrace = _trace;

    // Stop keydown propagation when focus is inside an input so window_event_listener
    // does not trigger editor shortcuts while the user is typing in a field.
    // Exception: arrow keys pass through when overlay align mode is active so they
    // can nudge the PDF overlay even if a panel input has focus.
    window.addEventListener('keydown', function(e) {
        var ae = document.activeElement;
        var tag = ae ? ae.tagName.toLowerCase() : '';
        var arrowKeys = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'];
        var isArrow = arrowKeys.indexOf(e.key) !== -1;
        var container = document.getElementById('viewport-container');
        var overlayAlignAttr = container ? container.dataset.overlayAlign : '(no-container)';
        var isFormField = (tag === 'input' || tag === 'textarea' || tag === 'select' ||
                           (ae && ae.isContentEditable));

        if (isArrow) {
            _trace('zoomguard_keydown_capture', {
                key: e.key,
                activeTag: tag,
                activeId: ae ? ae.id : null,
                activeType: ae ? ae.getAttribute('type') : null,
                activeClass: ae ? ae.className : null,
                overlayAlignAttr: overlayAlignAttr,
                isFormField: isFormField,
                ctrl: e.ctrlKey, shift: e.shiftKey, alt: e.altKey,
                defaultPrevented: e.defaultPrevented,
            });
        }

        if (isFormField) {
            if (isArrow) {
                if (container && container.dataset.overlayAlign === 'true') {
                    e.preventDefault();
                    ae.blur();
                    _trace('zoomguard_arrow_allow_blur', { key: e.key });
                    return;
                }
                _trace('zoomguard_arrow_BLOCKED_no_attr', {
                    key: e.key, overlayAlignAttr: overlayAlignAttr,
                });
            }
            e.stopImmediatePropagation();
        } else if (isArrow) {
            _trace('zoomguard_arrow_passthrough_no_input', {
                key: e.key, activeTag: tag,
            });
        }
    }, { capture: true });

    // Bubble-phase tracer — fires after Reflex's window_event_listener would
    // have run. If we see this but not the handle_key_event backend log,
    // Reflex's listener is not attached or was blocked upstream.
    window.addEventListener('keydown', function(e) {
        var arrowKeys = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'];
        if (arrowKeys.indexOf(e.key) !== -1) {
            _trace('zoomguard_keydown_bubble', {
                key: e.key,
                defaultPrevented: e.defaultPrevented,
                activeTag: document.activeElement ? document.activeElement.tagName.toLowerCase() : null,
            });
        }
    }, { capture: false });

    // ---------------------------------------------------------------------------
    // Global JS→Python dispatch bridge.
    // Reflex 0.8 does not expose window.applyEvent.  We extract addEvents from
    // the React fiber tree (EventLoopContext) so rx.script IIFEs can fire
    // backend events with proper socket/navigate/params wiring.
    // ---------------------------------------------------------------------------
    function _installApplyEvent() {
        var mod = window.__reflex && window.__reflex['$/utils/state'];
        if (!mod || !mod.ReflexEvent) { setTimeout(_installApplyEvent, 200); return; }
        // Find addEvents from React fiber of a known DOM element
        var el = document.getElementById('viewport-container') || document.querySelector('[id]');
        if (!el) { setTimeout(_installApplyEvent, 200); return; }
        var fiberKey = Object.keys(el).find(function(k) { return k.startsWith('__reactFiber'); });
        if (!fiberKey) { setTimeout(_installApplyEvent, 200); return; }
        var fiber = el[fiberKey], addEvents = null;
        for (var i = 0; i < 100 && fiber; i++, fiber = fiber.return) {
            var v = fiber.memoizedProps && fiber.memoizedProps.value;
            if (Array.isArray(v) && v.length === 2 && typeof v[0] === 'function') {
                addEvents = v[0]; break;
            }
        }
        if (!addEvents) { setTimeout(_installApplyEvent, 200); return; }
        var _addEvents = addEvents;
        window.applyEvent = function(eventName, payload) {
            var name = eventName.indexOf('.') === -1 ? eventName :
                'reflex___state____state.archilume_ui___state___editor_state____editor_state.' +
                eventName.replace('editor_state.', '');
            _addEvents([mod.ReflexEvent(name, payload || {})], [], {});
        };
        _trace('applyEvent_installed', {});
        _installViewportObserver();
    }
    _installApplyEvent();

    // ---------------------------------------------------------------------------
    // Viewport resize observer — previously lived in components/viewport.py as
    // its own rx.script. That script was either not mounting or not finding
    // the container before the ResizeObserver's "only on change" behaviour
    // locked viewport_width at 0 forever. Consolidated here because this IIFE
    // demonstrably runs (we see zoomguard traces) and applyEvent is in scope.
    // ---------------------------------------------------------------------------
    var _vpLastW = -1, _vpLastH = -1, _vpObserver = null;
    function _installViewportObserver() {
        var el = document.getElementById('viewport-container');
        if (!el) {
            _trace('viewport_observer_waiting', { reason: 'no-container' });
            setTimeout(_installViewportObserver, 200);
            return;
        }
        function _report() {
            var w = Math.round(el.clientWidth);
            var h = Math.round(el.clientHeight);
            if (w <= 0 || h <= 0) {
                _trace('viewport_report_skip_zero', { w: w, h: h });
                return;
            }
            if (w === _vpLastW && h === _vpLastH) return;
            _vpLastW = w; _vpLastH = h;
            try {
                window.applyEvent('editor_state.set_viewport_size', { data: { w: w, h: h } });
                _trace('viewport_resize_flush', { w: w, h: h });
            } catch (err) {
                _trace('viewport_resize_error', { err: String(err) });
            }
        }
        _report();
        // First report may have skipped (layout not settled yet). Poll a few
        // times to catch the moment the container gets its real dimensions.
        var tries = 0;
        (function _pollUntilSized() {
            if (_vpLastW > 0) return;
            _report();
            if (++tries < 30) setTimeout(_pollUntilSized, 100);
            else _trace('viewport_poll_gave_up', { tries: tries });
        })();
        _vpObserver = new ResizeObserver(function() { _report(); });
        _vpObserver.observe(el);
        _trace('viewport_observer_installed', {
            initialW: el.clientWidth, initialH: el.clientHeight,
        });
    }
})();
""")


# Global keyboard handler — captures keys not handled by input elements


def index() -> rx.Component:
    return rx.box(
        _ZOOM_GUARD_SCRIPT,
        rx.cond(EditorState.debug_mode, _DEBUG_SCRIPT),
        rx.window_event_listener(on_key_down=EditorState.handle_key_event),
        sidebar(),
        rx.flex(
            header(),
            rx.flex(
                project_tree(),
                rx.flex(
                    viewport(),
                    direction="column",
                    style={"flex": "1", "overflow": "hidden"},
                ),
                style={"flex": "1", "overflow": "hidden"},
            ),
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

    // Patch applyEvent to log dispatches (waits for bridge installed by _ZOOM_GUARD_SCRIPT)
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
        var ae = document.activeElement;
        var aeTag = ae ? ae.tagName.toLowerCase() : '(none)';
        var aeId = ae ? (ae.id || '(no-id)') : '';
        var container = document.getElementById('viewport-container');
        var overlayAlign = container ? container.dataset.overlayAlign : '(no-container)';
        log('key=' + e.key + ' active=' + aeTag + '#' + aeId +
            ' overlayAlign=' + overlayAlign);
        // Also mirror to backend log file via tracer, so we have a single
        // source of truth when analysing arrow-key failures.
        if (window._archilumeTrace && e.key.indexOf('Arrow') === 0) {
            window._archilumeTrace('debug_doc_keydown', {
                key: e.key, activeTag: aeTag, activeId: aeId,
                overlayAlignAttr: overlayAlign,
                ctrl: e.ctrlKey, shift: e.shiftKey,
                defaultPrevented: e.defaultPrevented,
            });
        }
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
