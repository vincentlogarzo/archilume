"""PdfUnderlayComponent — drives a single ``#overlay-canvas`` element with
pdf.js, replacing the prior PyMuPDF → PNG rasterisation pipeline.

Mounts as an invisible React Fragment that sits as a sibling next to the
canvas in the SVG viewport stack. The component does *not* own the canvas
DOM node — the canvas is rendered inline by ``viewport.py`` so the existing
``_CANVAS_JS`` (zoom/pan / Adjust-Plan-Mode drag, ``data-transform``
MutationObserver, etc.) keeps working unchanged. This component only:

* loads the ``pdfjs-dist`` library and bootstraps its worker once,
* watches ``#overlay-canvas`` for ``data-pdf-url`` mutations and opens /
  destroys ``PDFDocumentProxy`` instances on change,
* watches ``data-page-idx`` and ``data-render-scale`` for re-render triggers,
* polls ``window._archiZoom`` on a 200 ms interval and bumps
  ``data-render-scale`` (debounced) when sustained zoom-in raises the
  required pixel density by ≥1.5×,
* dispatches ``editor_state.set_overlay_pdf_loaded`` back into Reflex via
  ``EventLoopContext`` (no ``window.applyEvent`` global dependency — the
  context is consumed directly so the component is independent of mount
  ordering with ``ZoomGuardComponent``).

All effects guard against unmount races, cancel in-flight pdf.js render
tasks, and call ``doc.destroy()`` in cleanup so PDFDocumentProxy memory is
released between document swaps.
"""

from __future__ import annotations

from reflex.components.base.fragment import Fragment
from reflex.utils.imports import ImportDict, ImportVar
from reflex.vars.base import Var


_STATE_PREFIX = (
    "reflex___state____state"
    ".archilume_app___state___editor_state____editor_state"
)


class PdfUnderlayComponent(Fragment):
    """Invisible component that renders the attached PDF onto ``#overlay-canvas``.

    Renders as a React Fragment (no DOM element of its own).
    """

    def add_imports(self) -> ImportDict:
        # Named imports avoid Reflex's broken namespace-import code-gen
        # (``import {* as foo} from ...`` is a JS syntax error). We only need
        # ``getDocument`` and ``GlobalWorkerOptions`` from pdfjs-dist; pulling
        # them by name produces clean ``import {getDocument, ...}`` JSX.
        #
        # ``pdfjs-dist/build/pdf.worker.mjs?url`` is a Vite import-syntax
        # convention (the ``?url`` suffix returns the resolved asset URL at
        # build time) — it is *not* a real npm package and must be marked
        # ``install=False`` so Reflex's auto-add-to-package.json step does
        # not try to ``bun add`` it.
        return {
            "react": ["useContext", "useEffect", "useRef"],
            "$/utils/context": ["EventLoopContext"],
            "$/utils/state": ["ReflexEvent"],
            "pdfjs-dist": ["getDocument", "GlobalWorkerOptions"],
            "pdfjs-dist/build/pdf.worker.mjs?url": [
                ImportVar(tag="pdfWorkerUrl", is_default=True, install=False),
            ],
        }

    def add_hooks(self) -> list[str | Var]:
        return [
            "const [_pu_addEvents] = useContext(EventLoopContext);",
            "const _pu_state = useRef({ doc: null, docUrl: '', renderTask: null, lastScale: 0, pageWidthPts: 0, inFlight: false, pending: false });",
            f"""
useEffect(() => {{
    if (!GlobalWorkerOptions.workerSrc) {{
        GlobalWorkerOptions.workerSrc = pdfWorkerUrl;
    }}

    const canvas = document.getElementById('overlay-canvas');
    if (!canvas) return;

    let cancelled = false;
    const RENDER_SCALE_CAP = 4.0;
    // Absolute backing-buffer cap. ~32 MP ≈ 128 MB RGBA — comfortable for any
    // modern desktop browser. Without this, large architectural PDFs (e.g.
    // A0/A1 pages at zoom × dpr) can request bitmaps of hundreds of megapixels
    // and rapid zoom gestures stack multiple allocations before GC, freezing
    // Chrome's main thread ("This page isn't responding").
    const MAX_BITMAP_PIXELS = 32_000_000;
    const ZOOM_THRESHOLD = 1.5;
    const ZOOM_POLL_MS = 200;

    const dispatchLoaded = (payload) => {{
        try {{
            _pu_addEvents([ReflexEvent(
                '{_STATE_PREFIX}.set_overlay_pdf_loaded',
                {{payload: payload}}
            )], [], {{}});
        }} catch (e) {{
            console.warn('[pdf-underlay] dispatch set_overlay_pdf_loaded failed', e);
        }}
    }};

    const desiredRenderScale = () => {{
        const dpr = window.devicePixelRatio || 1;
        let z = 1;
        if (window._archiZoom && typeof window._archiZoom.getTransform === 'function') {{
            const t = window._archiZoom.getTransform();
            if (t && typeof t.zoom === 'number' && t.zoom > 0) z = t.zoom;
        }} else if (typeof window._archiZoom === 'number' && window._archiZoom > 0) {{
            z = window._archiZoom;
        }}
        return Math.min(RENDER_SCALE_CAP, Math.max(1, dpr * z));
    }};

    // Single-flight wrapper: collapses concurrent triggers (rapid zoom +
    // MutationObserver bursts) into at most one in-flight render plus one
    // queued follow-up. Without this, multiple ``renderActivePage`` calls
    // park on ``await getPage`` and then each allocate a fresh canvas
    // backing buffer in close succession — for a large PDF page that's
    // hundreds of MB per allocation, enough to freeze Chrome.
    const renderActivePage = () => {{
        const st = _pu_state.current;
        if (!st.doc || cancelled) return;
        if (st.inFlight) {{
            st.pending = true;
            return;
        }}
        st.inFlight = true;
        renderActivePageImpl().finally(() => {{
            st.inFlight = false;
            if (st.pending && !cancelled) {{
                st.pending = false;
                renderActivePage();
            }}
        }});
    }};

    const renderActivePageImpl = async () => {{
        const st = _pu_state.current;
        if (!st.doc || cancelled) return;
        const pageIdx = parseInt(canvas.dataset.pageIdx || '0', 10);
        const oneBased = Math.min(Math.max(1, pageIdx + 1), st.doc.numPages);
        if (st.renderTask) {{
            try {{ st.renderTask.cancel(); }} catch (_) {{}}
            st.renderTask = null;
        }}
        let page;
        try {{
            page = await st.doc.getPage(oneBased);
        }} catch (e) {{
            if (!cancelled) console.warn('[pdf-underlay] getPage failed', e);
            return;
        }}
        if (cancelled) return;
        // Compute render scale from on-screen size. ``getBoundingClientRect()``
        // returns the rect AFTER all ancestor transforms (including
        // ``transform: scale(_zoom)`` on ``#editor-canvas``), so
        // ``rect.width × dpr`` gives the exact device-pixel count the canvas
        // occupies on screen. Falls back to ``desiredRenderScale()`` when the
        // canvas has no layout box yet (during initial mount).
        let scale;
        const dpr = window.devicePixelRatio || 1;
        const naturalViewport = page.getViewport({{ scale: 1 }});
        st.pageWidthPts = naturalViewport.width;
        const rect = canvas.getBoundingClientRect();
        if (rect && rect.width > 0) {{
            scale = Math.min(RENDER_SCALE_CAP, (rect.width * dpr) / naturalViewport.width);
        }} else {{
            scale = desiredRenderScale();
        }}
        // Absolute bitmap-pixel cap. For very large PDF pages (architectural
        // A0/A1 drawings) the scale-based cap alone can still demand a 1 GB
        // bitmap — the OOM line for Chrome on most desktops. Reduce ``scale``
        // proportionally if the requested viewport exceeds MAX_BITMAP_PIXELS.
        let viewport = page.getViewport({{ scale: scale }});
        const wantedPixels = viewport.width * viewport.height;
        if (wantedPixels > MAX_BITMAP_PIXELS) {{
            const shrink = Math.sqrt(MAX_BITMAP_PIXELS / wantedPixels);
            scale = Math.max(1, scale * shrink);
            viewport = page.getViewport({{ scale: scale }});
        }}
        canvas.width = Math.round(viewport.width);
        canvas.height = Math.round(viewport.height);
        const ctx = canvas.getContext('2d');
        const task = page.render({{ canvasContext: ctx, viewport: viewport }});
        st.renderTask = task;
        st.lastScale = scale;
        try {{
            await task.promise;
        }} catch (e) {{
            if (e && e.name !== 'RenderingCancelledException' && !cancelled) {{
                console.warn('[pdf-underlay] render failed', e);
            }}
        }}
    }};

    const swapDocument = async (newUrl) => {{
        const st = _pu_state.current;
        if (st.docUrl === newUrl && st.doc) return;
        if (st.renderTask) {{
            try {{ st.renderTask.cancel(); }} catch (_) {{}}
            st.renderTask = null;
        }}
        if (st.doc) {{
            try {{ await st.doc.destroy(); }} catch (_) {{}}
            st.doc = null;
        }}
        st.docUrl = newUrl;
        if (!newUrl) return;
        try {{
            const doc = await getDocument(newUrl).promise;
            if (cancelled || st.docUrl !== newUrl) {{
                try {{ await doc.destroy(); }} catch (_) {{}}
                return;
            }}
            st.doc = doc;
            dispatchLoaded({{ ok: true, page_count: doc.numPages }});
            await renderActivePage();
        }} catch (e) {{
            if (!cancelled) {{
                dispatchLoaded({{ ok: false, error: 'Failed to load PDF in browser: ' + (e && e.message ? e.message : String(e)) }});
            }}
        }}
    }};

    swapDocument(canvas.dataset.pdfUrl || '');

    const observer = new MutationObserver((mutations) => {{
        for (const m of mutations) {{
            if (m.type !== 'attributes') continue;
            if (m.attributeName === 'data-pdf-url') {{
                swapDocument(canvas.dataset.pdfUrl || '');
                return;
            }}
            if (m.attributeName === 'data-page-idx' ||
                m.attributeName === 'data-render-scale') {{
                renderActivePage();
            }}
        }}
    }});
    observer.observe(canvas, {{
        attributes: true,
        attributeFilter: ['data-pdf-url', 'data-page-idx', 'data-render-scale'],
    }});

    const zoomTimer = setInterval(() => {{
        if (cancelled) return;
        const st = _pu_state.current;
        if (!st.doc || !st.pageWidthPts) return;
        // Compare in the same units ``renderActivePage`` writes to ``lastScale``
        // (rect-based physical px / page natural pt). Otherwise the ratio is
        // unitless garbage and the threshold either never trips or trips
        // continuously. ``getBoundingClientRect()`` already includes ancestor
        // transforms, so this naturally tracks ``#editor-canvas``'s zoom.
        const dpr = window.devicePixelRatio || 1;
        const rect = canvas.getBoundingClientRect();
        if (rect.width <= 0) return;
        const want = Math.min(RENDER_SCALE_CAP, (rect.width * dpr) / st.pageWidthPts);
        if (st.lastScale > 0 && want / st.lastScale >= ZOOM_THRESHOLD) {{
            // Bump data-render-scale so the MutationObserver triggers a single
            // debounced re-render; the value itself is informational, the
            // mutation is what matters.
            canvas.dataset.renderScale = want.toFixed(3);
        }}
    }}, ZOOM_POLL_MS);

    return () => {{
        cancelled = true;
        observer.disconnect();
        clearInterval(zoomTimer);
        const st = _pu_state.current;
        if (st.renderTask) {{
            try {{ st.renderTask.cancel(); }} catch (_) {{}}
            st.renderTask = null;
        }}
        if (st.doc) {{
            try {{ st.doc.destroy(); }} catch (_) {{}}
            st.doc = null;
        }}
        st.docUrl = '';
        st.lastScale = 0;
        st.pageWidthPts = 0;
        st.inFlight = false;
        st.pending = false;
    }};
}}, [_pu_addEvents]);
""",
        ]


pdf_underlay = PdfUnderlayComponent.create
