"""Debug infrastructure — logging, event tracing, and state-diff decorator.

Provides:
- ``logger`` — Python logger for backend debug output (terminal + file)
- ``debug_handler`` — decorator that logs state diffs before/after event handlers
- ``DebugTrace`` — ring-buffer trace writer that dumps to ``debug_trace.json``
- ``correlation_id`` / ``with_correlation_id`` — thread a short request ID
  through multi-step handler chains so async events can be reassembled.
- ``LOG_FILE_PATH`` / ``LOG_DIR`` — canonical location of the unified log.

Single trace file location (all backend logs + JS-bridged traces go here):
    ~/.archilume/logs/archilume_app.log

On rotation the previous session moves to ``archilume_app.log.1``. The
``debug_trace.json`` ring buffer lives next to the log when no active
project directory has been registered, and under the project directory
once one is loaded.

Toggle debug mode at runtime via ``EditorState.toggle_debug_mode`` or by
launching with ``ARCHILUME_DEBUG=1 reflex run``.
"""

import contextlib
import contextvars
import functools
import json
import logging
import logging.handlers
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

# ---------------------------------------------------------------------------
# Correlation ID — threaded through handler chains via contextvars so that
# yielded sub-handlers inherit the same ID without explicit plumbing.
# ---------------------------------------------------------------------------

correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "archilume_correlation_id", default="-"
)


def new_correlation_id() -> str:
    """Return a short, collision-resistant request ID (8 hex chars)."""
    return uuid.uuid4().hex[:8]


@contextlib.contextmanager
def with_correlation_id(rid: str | None = None) -> Iterator[str]:
    """Context manager: set correlation ID for the duration of the block.

    Any logger output inside the block automatically carries the ID via the
    ``_CorrelationFilter`` installed on the root logger.
    """
    rid = rid or new_correlation_id()
    token = correlation_id.set(rid)
    try:
        yield rid
    finally:
        correlation_id.reset(token)


class _CorrelationFilter(logging.Filter):
    """Injects the active correlation ID into every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        record.rid = correlation_id.get()
        return True


# ---------------------------------------------------------------------------
# Logger — writes to terminal AND to a rotating log file
# ---------------------------------------------------------------------------

logger = logging.getLogger("archilume_app")
logger.addFilter(_CorrelationFilter())

# Default to WARNING; toggle_debug_mode flips to DEBUG
_initial_level = (
    logging.DEBUG
    if os.environ.get("ARCHILUME_DEBUG", "").lower() in ("1", "true")
    else logging.WARNING
)
logger.setLevel(_initial_level)

# Unified trace location — ``~/.archilume/logs/`` matches the repo's
# existing ``~/.archilume_gcp_config.json`` user-state convention and keeps
# logs out of the working tree.
LOG_DIR: Path = Path(os.environ.get("ARCHILUME_LOG_DIR", str(Path.home() / ".archilume" / "logs")))
LOG_FILE_PATH: Path = LOG_DIR / "archilume_app.log"

try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass

_LOG_FORMAT = "%(asctime)s [%(levelname)s] [rid=%(rid)s] %(name)s — %(message)s"

# Console handler
_console = logging.StreamHandler()
_console.setFormatter(logging.Formatter(_LOG_FORMAT, "%H:%M:%S"))
logger.addHandler(_console)

# File handler — rotating log capped at 512 KB with 1 backup.
# The main file is always the *current* session's log. On rotation the
# previous session moves to ``.log.1`` — keeping the active file small
# enough to grep/share without pagination.
try:
    _file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE_PATH, mode="w", maxBytes=512_000, backupCount=1, encoding="utf-8",
    )
    _file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    _file_handler.setLevel(logging.DEBUG)  # always capture DEBUG to file
    logger.addHandler(_file_handler)
    logger.warning(f"[debug] unified trace file: {LOG_FILE_PATH}")
except OSError as exc:
    # e.g. read-only filesystem — silently skip file logging, but leave a
    # breadcrumb on the console so the user knows why the file is missing.
    logger.warning(f"[debug] file handler disabled: {exc}")


# ---------------------------------------------------------------------------
# Debug trace — structured JSON ring buffer
# ---------------------------------------------------------------------------

class DebugTrace:
    """In-memory ring buffer of event traces, periodically flushed to JSON."""

    def __init__(self, max_entries: int = 200) -> None:
        self.entries: list[dict[str, Any]] = []
        self.max_entries = max_entries
        # Default to the unified log directory so a trace file always exists
        # even before a project is loaded. ``set_project_path`` overrides this
        # once the user opens a project.
        self._trace_path: Path | None = LOG_DIR / "debug_trace.json"

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


# Dict keys whose values should be redacted before logging. Match on the
# *key* (case-insensitive substring) so we catch ``access_token``,
# ``AuthorizationHeader``, ``APIKey`` etc. without listing every variant.
_REDACT_KEY_RE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|authorization|bearer|private[_-]?key|credential)",
    re.IGNORECASE,
)


def _safe_repr(val: Any, _key: str | None = None) -> Any:
    """JSON-safe representation of event handler args, with PII redaction.

    Dict values whose key matches ``_REDACT_KEY_RE`` are replaced with
    ``"***"`` regardless of depth. Long strings are truncated to 120 chars.
    """
    if _key and _REDACT_KEY_RE.search(_key):
        return "***"
    if isinstance(val, tuple):
        val = list(val)
    if isinstance(val, (str, int, float, bool, type(None))):
        return val
    if isinstance(val, (list, tuple)):
        return [_safe_repr(v) for v in val]
    if isinstance(val, dict):
        return {str(k): _safe_repr(v, _key=str(k)) for k, v in val.items()}
    return str(val)[:120]
