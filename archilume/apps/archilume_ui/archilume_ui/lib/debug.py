"""Debug infrastructure — logging, event tracing, and state-diff decorator.

Provides:
- ``logger`` — Python logger for backend debug output (terminal + file)
- ``debug_handler`` — decorator that logs state diffs before/after event handlers
- ``DebugTrace`` — ring-buffer trace writer that dumps to ``debug_trace.json``

Toggle debug mode at runtime via ``EditorState.toggle_debug_mode`` or by
launching with ``ARCHILUME_DEBUG=1 reflex run``.
"""

import functools
import json
import logging
import logging.handlers
import os
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Logger — writes to terminal AND to a rotating log file
# ---------------------------------------------------------------------------

logger = logging.getLogger("archilume_ui")

# Default to WARNING; toggle_debug_mode flips to DEBUG
_initial_level = (
    logging.DEBUG
    if os.environ.get("ARCHILUME_DEBUG", "").lower() in ("1", "true")
    else logging.WARNING
)
logger.setLevel(_initial_level)

# Console handler
_console = logging.StreamHandler()
_console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
logger.addHandler(_console)

# File handler — rotating log capped at 512 KB with 1 backup.
# The main file is always the *current* session's log. On rotation the
# previous session moves to .log.1 — so Claude only needs to read the
# main file, which stays small enough to fit in context.
_LOG_DIR = Path(__file__).resolve().parent.parent.parent  # archilume_ui root
_LOG_FILE = _LOG_DIR / "archilume_ui_debug.log"

try:
    _file_handler = logging.handlers.RotatingFileHandler(
        _LOG_FILE, mode="w", maxBytes=512_000, backupCount=1, encoding="utf-8",
    )
    _file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s")
    )
    _file_handler.setLevel(logging.DEBUG)  # always capture DEBUG to file
    logger.addHandler(_file_handler)
except OSError:
    pass  # e.g. read-only filesystem — silently skip file logging


# ---------------------------------------------------------------------------
# Debug trace — structured JSON ring buffer
# ---------------------------------------------------------------------------

class DebugTrace:
    """In-memory ring buffer of event traces, periodically flushed to JSON."""

    def __init__(self, max_entries: int = 200) -> None:
        self.entries: list[dict[str, Any]] = []
        self.max_entries = max_entries
        self._trace_path: Path | None = None

    def set_project_path(self, project_dir: Path) -> None:
        """Set the output path for the trace file (inside project dir)."""
        self._trace_path = project_dir / "debug_trace.json"

    def add(self, event: str, args: Any = None, changes: dict | None = None) -> None:
        entry = {
            "ts": time.strftime("%H:%M:%S"),
            "event": event,
        }
        if args is not None:
            entry["args"] = _safe_repr(args)
        if changes:
            entry["changes"] = changes
        self.entries.append(entry)
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]

    def flush(self) -> None:
        """Write current buffer to disk."""
        if not self._trace_path or not self.entries:
            return
        try:
            self._trace_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._trace_path, "w", encoding="utf-8") as f:
                json.dump(self.entries, f, indent=2, default=str)
        except OSError:
            pass

    def get_recent(self, n: int = 50) -> list[dict[str, Any]]:
        """Return the last *n* entries (for UI display)."""
        return self.entries[-n:]

    def clear(self) -> None:
        self.entries.clear()


# Singleton trace instance
trace = DebugTrace()


# ---------------------------------------------------------------------------
# State-diff decorator
# ---------------------------------------------------------------------------

# Fields to snapshot for before/after comparison.
# Keep this short — only the fields you care about when debugging.
TRACKED_FIELDS: list[str] = [
    "draw_mode", "edit_mode", "divider_mode", "df_placement_mode",
    "ortho_snap", "overlay_visible", "overlay_align_mode",
    "selected_room_idx", "multi_selected_idxs",
    "current_hdr_idx", "current_variant_idx",
    "draw_vertices", "divider_points",
    "status_message",
]


def debug_handler(fn):
    """Decorator: logs state snapshot before/after an event handler.

    Only active when ``self.debug_mode`` is True on the state instance.
    Handles both regular methods and generator methods (those using ``yield``).
    """
    import inspect

    if inspect.isgeneratorfunction(fn):

        @functools.wraps(fn)
        def gen_wrapper(self, *args, **kwargs):
            if not getattr(self, "debug_mode", False):
                yield from fn(self, *args, **kwargs)
                return

            name = fn.__name__
            before = _snapshot(self)
            logger.debug(f"▶ {name}({_safe_repr(args)}) — enter (generator)")

            yield from fn(self, *args, **kwargs)

            after = _snapshot(self)
            changes = _diff(before, after)
            if changes:
                logger.debug(f"◀ {name} — changed: {changes}")
                trace.add(name, args=args, changes=changes)
            else:
                logger.debug(f"◀ {name} — no state changes")
                trace.add(name, args=args)
            trace.flush()

        return gen_wrapper

    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        if not getattr(self, "debug_mode", False):
            return fn(self, *args, **kwargs)

        name = fn.__name__
        before = _snapshot(self)
        logger.debug(f"▶ {name}({_safe_repr(args)}) — enter")

        result = fn(self, *args, **kwargs)

        after = _snapshot(self)
        changes = _diff(before, after)
        if changes:
            logger.debug(f"◀ {name} — changed: {changes}")
            trace.add(name, args=args, changes=changes)
        else:
            logger.debug(f"◀ {name} — no state changes")
            trace.add(name, args=args)

        trace.flush()
        return result

    return wrapper


def _snapshot(state) -> dict[str, Any]:
    """Capture tracked fields from a state instance."""
    out = {}
    for field in TRACKED_FIELDS:
        try:
            val = getattr(state, field)
            # Shallow copy lists so we compare against the original
            if isinstance(val, list):
                val = list(val)
            elif isinstance(val, dict):
                val = dict(val)
            out[field] = val
        except AttributeError:
            pass
    return out


def _diff(before: dict, after: dict) -> dict[str, tuple]:
    """Return fields that changed, as {field: [old, new]}."""
    changes = {}
    for key in before:
        b, a = before[key], after.get(key)
        if b != a:
            changes[key] = [_summarize(b), _summarize(a)]
    return changes


def _summarize(val: Any) -> Any:
    """Produce a short JSON-safe summary of a value."""
    if isinstance(val, list):
        if len(val) > 5:
            return f"list[{len(val)}]"
        return val
    if isinstance(val, dict):
        if len(val) > 5:
            return f"dict[{len(val)} keys]"
        return val
    return val


def _safe_repr(val: Any) -> Any:
    """JSON-safe representation of event handler args."""
    if isinstance(val, tuple):
        val = list(val)
    if isinstance(val, (str, int, float, bool, type(None))):
        return val
    if isinstance(val, (list, tuple)):
        return [_safe_repr(v) for v in val]
    if isinstance(val, dict):
        return {str(k): _safe_repr(v) for k, v in val.items()}
    return str(val)[:120]
