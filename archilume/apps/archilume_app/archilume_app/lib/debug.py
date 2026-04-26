"""Debug infrastructure — logging, event tracing, state-diff decorator.

Provides:

- ``logger`` — Python logger writing to terminal + rotating file.
- ``DEBUG_TIER`` / ``set_debug_tier`` — tiered verbosity (``off``/``light``/``verbose``).
- ``debug_handler`` — decorator that times handlers and (in ``verbose``) diffs state.
- ``auto_debug_instrument`` — class decorator that wraps every public method.
- ``DebugTrace`` — bounded ring buffer with async, debounced disk flush.
- ``correlation_id`` / ``with_correlation_id`` — thread a short request ID
  through multi-step handler chains so async events can be reassembled.
- ``LOG_FILE_PATH`` / ``LOG_DIR`` — canonical location of the unified log.

Single trace file location (all backend logs + JS-bridged traces go here):

    ~/.archilume/logs/archilume_app.log

On rotation prior sessions move to ``archilume_app.log.1`` … ``.log.5``. The
``debug_trace.json`` ring buffer lives next to the log when no active project
directory has been registered, and under the project directory once one is
loaded. Entries that fall off the ring buffer are appended to
``debug_trace.archive.jsonl`` for long-running-session forensics.

The tier is set once at import from the ``ARCHILUME_DEBUG`` env var:

- unset / any other value → ``light`` (default-on; near-zero per-call cost)
- ``0`` → ``off`` (pure pass-through)
- ``1`` or ``verbose`` → ``verbose`` (full state-diff)

``set_debug_tier`` flips it at runtime if needed.
"""

from __future__ import annotations

import atexit
import contextlib
import contextvars
import functools
import inspect
import json
import logging
import logging.handlers
import os
import queue
import re
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterator, Literal

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
    """Set the correlation ID for the duration of the block."""
    rid = rid or new_correlation_id()
    token = correlation_id.set(rid)
    try:
        yield rid
    finally:
        correlation_id.reset(token)


class _CorrelationFilter(logging.Filter):
    """Inject the active correlation ID into every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        record.rid = correlation_id.get()
        return True


# ---------------------------------------------------------------------------
# Tier configuration
# ---------------------------------------------------------------------------

DebugTier = Literal["off", "light", "verbose"]

_TIER_FROM_ENV = {"0": "off", "false": "off", "1": "verbose", "verbose": "verbose"}
DEBUG_TIER: DebugTier = _TIER_FROM_ENV.get(  # type: ignore[assignment]
    os.environ.get("ARCHILUME_DEBUG", "").lower(), "light"
)


def set_debug_tier(tier: DebugTier) -> None:
    """Set the tier at runtime. Validated; no-ops on unknown values."""
    global DEBUG_TIER
    if tier in ("off", "light", "verbose"):
        DEBUG_TIER = tier
        logger.warning(f"[debug] tier set to {tier}")


# ---------------------------------------------------------------------------
# Logger — rotating file + console
# ---------------------------------------------------------------------------

logger = logging.getLogger("archilume_app")
logger.addFilter(_CorrelationFilter())
logger.setLevel(logging.DEBUG if DEBUG_TIER == "verbose" else logging.WARNING)

LOG_DIR: Path = Path(os.environ.get("ARCHILUME_LOG_DIR", str(Path.home() / ".archilume" / "logs")))
LOG_FILE_PATH: Path = LOG_DIR / "archilume_app.log"

try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass

_LOG_FORMAT = "%(asctime)s [%(levelname)s] [rid=%(rid)s] %(name)s — %(message)s"
_LOG_MAX_BYTES = 2_000_000
_LOG_BACKUP_COUNT = 5

_console = logging.StreamHandler()
_console.setFormatter(logging.Formatter(_LOG_FORMAT, "%H:%M:%S"))
logger.addHandler(_console)

_file_handler: logging.handlers.RotatingFileHandler | None = None


def _install_file_handler(path: Path, *, mode: str = "w") -> bool:
    """Open a rotating file handler at ``path``.

    ``mode='w'`` truncates on session start (fresh log per launch).
    ``mode='a'`` is used when relocating mid-session so we don't lose history.
    Returns True on success, False if the filesystem rejected the path.
    """
    global _file_handler, LOG_DIR, LOG_FILE_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            path, mode=mode, maxBytes=_LOG_MAX_BYTES,
            backupCount=_LOG_BACKUP_COUNT, encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        handler.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        _file_handler = handler
        LOG_DIR = path.parent
        LOG_FILE_PATH = path
        return True
    except OSError as exc:
        logger.warning(f"[debug] file handler at {path} disabled: {exc}")
        return False


if _install_file_handler(LOG_FILE_PATH, mode="w"):
    logger.warning(f"[debug] unified trace file: {LOG_FILE_PATH} (tier={DEBUG_TIER})")


def relocate_to_project(project_dir: Path) -> Path:
    """Move all debug artefacts into ``<project_dir>/logs/``.

    Single hook that runs when the Reflex app loads a project. Swaps the
    rotating file handler and points ``DebugTrace`` at the same folder so
    log + trace + archive land together — the user can zip
    ``<project_dir>/logs/`` and share it as a single bug-report bundle.

    Returns the new logs directory. Idempotent: calling with the same
    project_dir twice is a no-op apart from the breadcrumb log line.
    """
    global _file_handler
    logs_dir = Path(project_dir) / "logs"
    new_log_path = logs_dir / "archilume_app.log"

    if _file_handler is not None and Path(_file_handler.baseFilename) == new_log_path:
        return logs_dir

    # Tear down old handler so the OS releases the file (matters on Windows
    # where an open file blocks moves/zips by another process).
    if _file_handler is not None:
        try:
            logger.removeHandler(_file_handler)
            _file_handler.close()
        except Exception:  # noqa: BLE001
            pass
        _file_handler = None

    if _install_file_handler(new_log_path, mode="a"):
        logger.warning(f"[debug] log relocated to project: {new_log_path}")
    trace.set_project_path(logs_dir)
    return logs_dir


# ---------------------------------------------------------------------------
# DebugTrace — bounded ring buffer with async debounced flush
# ---------------------------------------------------------------------------

_FLUSH_INTERVAL_S = 0.5
_FLUSH_BATCH = 50


class DebugTrace:
    """Bounded ring buffer of event traces. Hot-path append is non-blocking;
    a daemon thread debounces JSON writes off the request thread."""

    def __init__(self, max_entries: int = 1000) -> None:
        self.max_entries = max_entries
        self.entries: deque[dict[str, Any]] = deque(maxlen=max_entries)
        self._trace_path: Path = LOG_DIR / "debug_trace.json"
        self._archive_path: Path = LOG_DIR / "debug_trace.archive.jsonl"
        self._dirty = threading.Event()
        self._archive_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._start_writer()

    def set_project_path(self, project_dir: Path) -> None:
        """Move the active trace file under the loaded project."""
        self._trace_path = project_dir / "debug_trace.json"
        self._archive_path = project_dir / "debug_trace.archive.jsonl"

    def add(self, event: str, args: Any = None, changes: dict | None = None,
            elapsed_ms: float | None = None) -> None:
        entry: dict[str, Any] = {
            "ts": time.strftime("%H:%M:%S"),
            "event": event,
            "rid": correlation_id.get(),
        }
        if elapsed_ms is not None:
            entry["elapsed_ms"] = round(elapsed_ms, 3)
        if args is not None:
            entry["args"] = _safe_repr(args)
        if changes:
            entry["changes"] = changes
        # If full, the about-to-be-evicted entry needs to land in the archive.
        if len(self.entries) == self.max_entries:
            self._archive_queue.put_nowait(self.entries[0])
        self.entries.append(entry)
        self._dirty.set()

    def flush(self) -> None:
        """Write the current buffer to disk synchronously (for shutdown / tests)."""
        if not self.entries:
            return
        snapshot = list(self.entries)
        try:
            self._trace_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._trace_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2, default=str)
        except OSError:
            pass
        # Drain whatever has accumulated for the archive.
        self._drain_archive()

    def get_recent(self, n: int = 50) -> list[dict[str, Any]]:
        return list(self.entries)[-n:]

    def clear(self) -> None:
        self.entries.clear()

    # ------------------- async writer -------------------

    def _start_writer(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        t = threading.Thread(target=self._writer_loop, name="debug-trace-flush", daemon=True)
        t.start()
        self._thread = t

    def _writer_loop(self) -> None:
        last_flush = time.monotonic()
        while not self._stop.is_set():
            triggered = self._dirty.wait(timeout=_FLUSH_INTERVAL_S)
            if not triggered:
                continue
            self._dirty.clear()
            # Debounce: coalesce bursts within _FLUSH_INTERVAL_S.
            now = time.monotonic()
            if (now - last_flush) < _FLUSH_INTERVAL_S and len(self.entries) < _FLUSH_BATCH:
                continue
            last_flush = now
            self.flush()

    def _drain_archive(self) -> None:
        try:
            with open(self._archive_path, "a", encoding="utf-8") as f:
                while True:
                    try:
                        item = self._archive_queue.get_nowait()
                    except queue.Empty:
                        break
                    f.write(json.dumps(item, default=str) + "\n")
        except OSError:
            pass


# Singleton trace instance
trace = DebugTrace()
atexit.register(trace.flush)


# ---------------------------------------------------------------------------
# Field discovery (verbose tier) — cached per state class
# ---------------------------------------------------------------------------

# Fields too noisy or framework-internal to track in the diff.
UNTRACKED_FIELDS: set[str] = {
    "router", "is_hydrated",
    "dirty_substates", "dirty_vars",
    "debug_log",  # the trace's own buffer — avoid self-recursion
    "status_colour",  # cosmetic, changes constantly
}

_SNAPSHOT_FIELDS_CACHE: dict[type, tuple[str, ...]] = {}


def _is_class_descriptor(cls_attr: Any) -> bool:
    """True for properties, classmethod/staticmethod, and Reflex computed vars.

    These should never appear in snapshots — they aren't state, and reading
    them can be expensive (computed vars run user code on every access).
    """
    if isinstance(cls_attr, (property, classmethod, staticmethod)):
        return True
    if inspect.isfunction(cls_attr) or inspect.ismethod(cls_attr):
        return True
    # Reflex-style markers (defensive — reflex changes its var marker between versions)
    for attr in ("_var_data", "__rx_var__", "_var_name"):
        if hasattr(cls_attr, attr):
            return True
    return False


def _discover_tracked_fields(state: Any) -> tuple[str, ...]:
    """Return the names of fields to snapshot for this state instance.

    Class-level fields (annotations, defaults) are discovered once and cached.
    Instance-level fields (``vars(state)``) are unioned in on every call —
    cheap, and necessary so that ad-hoc attributes (and SimpleNamespace tests)
    are picked up.
    """
    cls = type(state)
    cls_fields = _SNAPSHOT_FIELDS_CACHE.get(cls)
    if cls_fields is None:
        candidates: set[str] = set()
        for klass in cls.__mro__:
            candidates.update(getattr(klass, "__annotations__", {}).keys())
            candidates.update(vars(klass).keys())
        kept: list[str] = []
        for name in candidates:
            if name.startswith("_") or name in UNTRACKED_FIELDS:
                continue
            cls_attr = None
            for klass in cls.__mro__:
                if name in vars(klass):
                    cls_attr = vars(klass)[name]
                    break
            if cls_attr is not None and _is_class_descriptor(cls_attr):
                continue
            kept.append(name)
        cls_fields = tuple(sorted(kept))
        _SNAPSHOT_FIELDS_CACHE[cls] = cls_fields

    instance_fields = (
        n for n in vars(state).keys()
        if not n.startswith("_") and n not in UNTRACKED_FIELDS
    )
    merged = set(cls_fields).union(instance_fields)
    return tuple(sorted(merged))


def _snapshot(state: Any) -> dict[str, Any]:
    """Capture the current value of every tracked field (verbose tier only)."""
    out: dict[str, Any] = {}
    for name in _discover_tracked_fields(state):
        try:
            val = getattr(state, name)
        except Exception:
            continue
        if callable(val):
            continue
        if isinstance(val, list):
            val = list(val)
        elif isinstance(val, dict):
            val = dict(val)
        out[name] = val
    return out


def _diff(before: dict, after: dict) -> dict[str, list[Any]]:
    """Fields that changed, as ``{field: [old, new]}`` (summarised)."""
    changes: dict[str, list[Any]] = {}
    for key in before:
        b, a = before[key], after.get(key)
        if b != a:
            changes[key] = [_summarize(b), _summarize(a)]
    return changes


def _summarize(val: Any) -> Any:
    """Short JSON-safe summary of a value."""
    if isinstance(val, list):
        if len(val) > 5:
            return f"list[{len(val)}]"
        return val
    if isinstance(val, dict):
        if len(val) > 5:
            return f"dict[{len(val)} keys]"
        return val
    return val


_REDACT_KEY_RE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|authorization|bearer|private[_-]?key|credential)",
    re.IGNORECASE,
)


def _safe_repr(val: Any, _key: str | None = None) -> Any:
    """JSON-safe representation of args, with PII redaction and length cap."""
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


# ---------------------------------------------------------------------------
# Decorator — tiered cost model
# ---------------------------------------------------------------------------

def debug_handler(fn: Callable) -> Callable:
    """Wrap an event handler with tiered tracing.

    - ``off`` tier: pass-through, zero overhead beyond a global read.
    - ``light`` tier: time the call, queue a minimal entry. ~µs.
    - ``verbose`` tier: snapshot before/after, diff, redact args. ~10–100 µs.

    Handles both regular methods and generator (``yield``-using) methods.
    """
    if inspect.isgeneratorfunction(fn):

        @functools.wraps(fn)
        def gen_wrapper(self, *args, **kwargs):
            tier = DEBUG_TIER
            if tier == "off":
                yield from fn(self, *args, **kwargs)
                return
            name = fn.__name__
            t0 = time.perf_counter()
            if tier == "verbose":
                before = _snapshot(self)
                logger.debug(f"▶ {name}({_safe_repr(args)}) — enter (gen)")
                yield from fn(self, *args, **kwargs)
                after = _snapshot(self)
                changes = _diff(before, after)
                elapsed = (time.perf_counter() - t0) * 1000
                trace.add(name, args=args, changes=changes or None, elapsed_ms=elapsed)
                if changes:
                    logger.debug(f"◀ {name} — {elapsed:.1f}ms — changed: {changes}")
                else:
                    logger.debug(f"◀ {name} — {elapsed:.1f}ms — no state changes")
            else:  # light
                yield from fn(self, *args, **kwargs)
                trace.add(name, elapsed_ms=(time.perf_counter() - t0) * 1000)

        return gen_wrapper

    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        tier = DEBUG_TIER
        if tier == "off":
            return fn(self, *args, **kwargs)
        name = fn.__name__
        t0 = time.perf_counter()
        if tier == "verbose":
            before = _snapshot(self)
            logger.debug(f"▶ {name}({_safe_repr(args)}) — enter")
            result = fn(self, *args, **kwargs)
            after = _snapshot(self)
            changes = _diff(before, after)
            elapsed = (time.perf_counter() - t0) * 1000
            trace.add(name, args=args, changes=changes or None, elapsed_ms=elapsed)
            if changes:
                logger.debug(f"◀ {name} — {elapsed:.1f}ms — changed: {changes}")
            else:
                logger.debug(f"◀ {name} — {elapsed:.1f}ms — no state changes")
            return result
        # light
        result = fn(self, *args, **kwargs)
        trace.add(name, elapsed_ms=(time.perf_counter() - t0) * 1000)
        return result

    return wrapper


# ---------------------------------------------------------------------------
# Class decorator — auto-instrument every public event handler
# ---------------------------------------------------------------------------

def auto_debug_instrument(*, exclude: set[str] | frozenset[str] = frozenset()):
    """Class decorator: wrap every public *function* attribute with ``debug_handler``.

    Skips: dunder/private methods, names in ``exclude``, descriptors / properties /
    Reflex computed vars, and anything that isn't a plain function (so already-wrapped
    methods are wrapped a second time — fine, decorator is idempotent in behaviour).
    """
    def decorate(cls: type) -> type:
        for name, attr in list(vars(cls).items()):
            if name.startswith("_"):
                continue
            if name in exclude:
                continue
            if not inspect.isfunction(attr):
                continue
            setattr(cls, name, debug_handler(attr))
        return cls
    return decorate


# ---------------------------------------------------------------------------
# log_event — emit a structured log line + trace entry in one call
# ---------------------------------------------------------------------------

def log_event(tag: str, **fields: Any) -> None:
    """Emit a single structured event to both the log and the trace buffer.

    In ``light`` and ``verbose`` tiers an entry is queued. In ``light`` only
    the trace entry is queued (no log line — keeps the log file lean). The
    log level is INFO by default; pass ``level="error"`` to escalate.
    """
    if DEBUG_TIER == "off":
        return
    level = str(fields.pop("level", "info")).lower()
    if DEBUG_TIER == "verbose":
        msg = f"[{tag}] " + " ".join(f"{k}={_safe_repr(v)}" for k, v in fields.items())
        getattr(logger, level if level in ("debug", "info", "warning", "error") else "info")(msg)
    elif level == "error":
        # Errors are too important to suppress in light tier.
        msg = f"[{tag}] " + " ".join(f"{k}={_safe_repr(v)}" for k, v in fields.items())
        logger.error(msg)
    trace.add(tag, args=fields if fields else None)


# ---------------------------------------------------------------------------
# Backwards-compatible alias retained for tests; static list is unused now
# but downstream importers may still reference it.
# ---------------------------------------------------------------------------

TRACKED_FIELDS: list[str] = []  # dynamic discovery replaces the static list
