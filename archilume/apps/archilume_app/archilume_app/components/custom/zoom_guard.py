"""ZoomGuardComponent — blocks browser pinch-zoom, guards keyboard in inputs,
and installs the global window.applyEvent dispatch bridge via EventLoopContext.

Replaces the former _ZOOM_GUARD_SCRIPT rx.script() IIFE with proper React
lifecycle management (useEffect + cleanup).
"""

from __future__ import annotations

from reflex.components.base.fragment import Fragment
from reflex.utils.imports import ImportDict
from reflex.vars.base import Var


# Fully-qualified Reflex event name prefix for EditorState.
_STATE_PREFIX = (
    "reflex___state____state"
    ".archilume_app___state___editor_state____editor_state"
)


class ZoomGuardComponent(Fragment):
    """Invisible component that installs global browser-zoom prevention,
    input-focus keyboard guard, and the JS→Python dispatch bridge.

    Renders as a React Fragment (no DOM element).
    Must be mounted once, near the root of the page.
    """

    def add_imports(self) -> ImportDict:
        return {
            "react": ["useContext", "useEffect"],
            "$/utils/context": ["EventLoopContext"],
            "$/utils/state": ["ReflexEvent"],
        }

    def add_hooks(self) -> list[str | Var]:
        return [
            # --- Obtain addEvents from React context (replaces fiber hack) ---
            "const [_zg_addEvents] = useContext(EventLoopContext);",

            # --- Install window.applyEvent bridge ---
            f"""
useEffect(() => {{
    window.applyEvent = function(eventName, payload) {{
        var name = eventName.indexOf('.') === -1
            ? eventName
            : '{_STATE_PREFIX}.' + eventName.replace('editor_state.', '');
        _zg_addEvents([ReflexEvent(name, payload || {{}})], [], {{}});
    }};
    return () => {{ delete window.applyEvent; }};
}}, [_zg_addEvents]);
""",

            # --- Block browser pinch-zoom and Ctrl+wheel ---
            """
useEffect(() => {
    const onWheel = (e) => { if (e.ctrlKey) e.preventDefault(); };
    const onGestureStart = (e) => { e.preventDefault(); };
    const onGestureChange = (e) => { e.preventDefault(); };
    const onTouchMove = (e) => { if (e.touches.length > 1) e.preventDefault(); };

    window.addEventListener('wheel', onWheel, { passive: false });
    window.addEventListener('gesturestart', onGestureStart, { passive: false });
    window.addEventListener('gesturechange', onGestureChange, { passive: false });
    window.addEventListener('touchmove', onTouchMove, { passive: false });

    return () => {
        window.removeEventListener('wheel', onWheel);
        window.removeEventListener('gesturestart', onGestureStart);
        window.removeEventListener('gesturechange', onGestureChange);
        window.removeEventListener('touchmove', onTouchMove);
    };
}, []);
""",

            # --- Guard keydown in inputs (capture phase) ---
            """
useEffect(() => {
    const onKeyDown = (e) => {
        const tag = document.activeElement
            ? document.activeElement.tagName.toLowerCase()
            : '';
        if (
            tag === 'input' || tag === 'textarea' || tag === 'select' ||
            (document.activeElement && document.activeElement.isContentEditable)
        ) {
            e.stopImmediatePropagation();
        }
    };
    window.addEventListener('keydown', onKeyDown, { capture: true });
    return () => {
        window.removeEventListener('keydown', onKeyDown, { capture: true });
    };
}, []);
""",
        ]


zoom_guard = ZoomGuardComponent.create
