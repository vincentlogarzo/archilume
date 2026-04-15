"""ProjectTreeResizeComponent — drag-to-resize handle for the project tree panel.

Replaces the former _RESIZE_SCRIPT rx.script() IIFE with proper React
lifecycle management (useEffect + cleanup). No MutationObserver needed —
the component re-mounts when Reflex re-renders.
"""

from __future__ import annotations

from reflex.components.base.fragment import Fragment
from reflex.utils.imports import ImportDict
from reflex.vars.base import Var


class ProjectTreeResizeComponent(Fragment):
    """Invisible component that enables drag-to-resize on the project tree panel.

    Expects two sibling DOM elements with specific IDs:
    - ``#project-tree-resize-handle`` — the narrow draggable edge
    - ``#project-tree-panel`` — the panel whose width is adjusted

    Renders as a React Fragment (no DOM element).
    """

    def add_imports(self) -> ImportDict:
        return {"react": ["useEffect", "useRef"]}

    def add_hooks(self) -> list[str | Var]:
        return [
            """
useEffect(() => {
    let dragging = false, startX = 0, startW = 0, activePanel = null;

    const onMouseMove = (e) => {
        if (!dragging || !activePanel) return;
        const newW = Math.min(600, Math.max(160, startW + (e.clientX - startX)));
        activePanel.style.width = newW + 'px';
    };

    const onMouseUp = () => {
        if (!dragging) return;
        dragging = false;
        activePanel = null;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
    };

    const onMouseDown = (e) => {
        const panel = document.getElementById('project-tree-panel');
        if (!panel) return;
        dragging = true;
        startX = e.clientX;
        startW = panel.getBoundingClientRect().width;
        activePanel = panel;
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        e.preventDefault();
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);

    const handle = document.getElementById('project-tree-resize-handle');
    if (handle) handle.addEventListener('mousedown', onMouseDown);

    return () => {
        window.removeEventListener('mousemove', onMouseMove);
        window.removeEventListener('mouseup', onMouseUp);
        if (handle) handle.removeEventListener('mousedown', onMouseDown);
    };
}, []);
""",
        ]


project_tree_resize = ProjectTreeResizeComponent.create
