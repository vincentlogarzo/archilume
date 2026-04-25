---
name: verify-ui
description: Post-edit validation skill for Reflex UI and state changes. Reads live logs, debug trace, and runs tests to confirm a change behaved as expected. Must be called after every edit to archilume_app state, event handlers, or UI components.
origin: local
---

# Verify UI Skill

Run this after every change to Reflex state, event handlers, computed vars, or UI components. It reads the monitoring infrastructure already built into the app to confirm the change is working correctly.

## When to Use

- After editing any file in `archilume/apps/archilume_app/archilume_app/`
- After adding or modifying a state event handler or computed var
- After adding or changing a UI component
- Before marking a feature task complete

## Prerequisite

The app must be running. The default tier is now `light` (auto-on every run);
upgrade to verbose only when chasing a specific bug:

```bash
# default-on, lean traces — every run, no env var needed:
python examples/launch_archilume_app.py --ensure
# verbose tier — full state diff + args, slower but more signal:
ARCHILUME_DEBUG=1 python examples/launch_archilume_app.py --ensure
```

---

## Where the logs live

After a project is loaded, all debug artefacts land in `<project_dir>/logs/`:

- `archilume_app.log` (+ rotations `.log.1` … `.log.5`)
- `debug_trace.json` — current ring buffer
- `debug_trace.archive.jsonl` — overflow archive

The whole folder can be zipped and shared if a user wants to send their
session for off-line analysis.

Before a project loads, the same files live in `~/.archilume/logs/`
(Linux/macOS) or `%USERPROFILE%\.archilume\logs\` (Windows).

In the steps below, ``<logs>`` means whichever of those two paths is
populated for the user's current session.

---

## Step 0 — Capture a baseline (optional but preferred)

Before exercising the change in the browser, snapshot the current trace as a
baseline. Step 2's diff then proves the change actually moved state, not just
"the log is quiet":

```bash
cp <logs>/debug_trace.json <logs>/debug_trace.baseline.json
```

Skip this step only when the change is purely additive UI (e.g. a new label)
with no state mutation.

---

## Step 1 — Read the log tail

Read the last 100 lines of the app log:

```bash
# Linux / macOS
tail -n 100 <logs>/archilume_app.log
# Windows PowerShell
Get-Content <logs>\archilume_app.log -Tail 100
```

**Look for:**

- Any `[ERROR]` or `[CRITICAL]` lines that appeared after the change
- Tracebacks (`Traceback (most recent call last)`) referencing modified files
- The expected event handler name appearing with `[DEBUG]` level entries
- Missing events that should have fired (absence of expected log lines)
- `[rid=XXXXXXXX]` correlation IDs — if an error appears, grep the same rid to trace the full chain

**Flag if:** Any new ERROR/CRITICAL lines, any traceback referencing the changed file.

---

## Step 2 — Diff the debug trace against baseline

Read both the baseline (if Step 0 captured one) and the current trace:

```
Read: <logs>/debug_trace.baseline.json   (from Step 0)
Read: <logs>/debug_trace.json            (current)
```

Each entry has:
- `ts`, `rid` — timestamp and correlation ID
- `event` — event handler name
- `elapsed_ms` — handler latency (`light` and `verbose` tiers)
- `args` — call arguments, redacted (`verbose` tier only)
- `changes` — `{field: [before, after]}` (`verbose` tier only)

**Compute the delta** — entries present in current but not in baseline. Group
the delta by `rid` to reconstruct the chain of handlers the change triggered.

**Verify:**

- The expected event handler appears in the delta (not just somewhere in the
  full trace — it must have fired *during the change*).
- State fields changed to the expected values (`before → after` in the delta).
- No unexpected fields were mutated.
- Event sequence is correct — order by `ts` within each `rid`.
- `elapsed_ms` is reasonable (e.g. < 50ms for a UI handler — flag p95 > 100ms).

**Flag if:** expected event absent from the delta, wrong fields changed,
unexpected mutations, or any handler shows latency > 100ms.

If the trace is in `light` tier (no `args`/`changes`), confirm at least that
the expected event names appear in the delta. Re-run with verbose tier only
if the light delta is ambiguous.

---

## Step 3 — Check for JS errors in the log

Browser-side errors and `console.error`/`console.warn` are now piped into the
unified backend log automatically (see `archilume_app.py`'s `_ZOOM_GUARD_SCRIPT`
error bridge). Grep the log tail from Step 1 for:

```
[ERROR] [JS:js_error]              — uncaught browser errors
[ERROR] [JS:js_unhandled_rejection] — unhandled Promise rejections
[DEBUG] [JS:js_console] level=error — explicit console.error calls
[DEBUG] [JS:js_console] level=warn  — explicit console.warn calls
```

Categorise any matches:
- `TypeError` / `ReferenceError` — JS-level bug in a component prop or event binding
- `WebSocket closed` — backend crashed mid-session; check log for traceback
- Reflex `hydration` warnings — state shape mismatch; likely a computed var or
  state field type issue

If none of these tags appear in the delta window, treat the console as clean —
no need to ask the user to copy-paste from DevTools. (Fall back to asking only
if the bridge appears not to be installed: search the log for the line
`[applyEvent_installed]` near the start of the session.)

---

## Step 4 — Run the test suite

```bash
cd archilume/apps/archilume_app
uv run pytest tests/ -x -q 2>&1
```

All existing tests must pass. If any fail:
- A pre-existing test broke → the change introduced a regression. Do not mark complete. Fix first.
- A new test fails → implementation does not match expected behaviour. Fix implementation.

**Target:** 0 failures, 0 errors. Warnings are acceptable.

---

## Step 5 — Report

Produce a concise verification report:

```
VERIFY-UI REPORT
================

Log check:    [PASS / FAIL — reason]
Trace check:  [PASS / FAIL — expected event: X, fields changed: Y → Z]
Console:      [CLEAN / errors reported]
Tests:        [PASS — N tests | FAIL — N failed]

Overall:      [READY / NEEDS FIX]

Issues:
1. ...
```

If Overall = NEEDS FIX, do not mark the task complete. Fix the flagged issues and re-run this skill.

---

## Testing Mandate

Every new or modified feature must ship with tests. These go in `archilume/apps/archilume_app/tests/`.

| Change | Required test coverage |
|--------|----------------------|
| New state field | Initial value; setter event sets it correctly |
| New event handler | Valid input → expected state changes; edge/guard cases |
| Modified handler | New behaviour; regression on old golden path |
| New computed var | Correct derivation from each relevant state combination |
| New UI component | Component renders; interaction fires expected event |
| New validation rule | Passing case; each failing case caught |

Tests use AAA structure (Arrange → Act → Assert). For generators/yielding handlers, assert the yield sequence. Tests prove the input→event→state-change chain is correct.

Example:

```python
import pytest
from archilume_app.state.editor_state import EditorState

@pytest.mark.asyncio
async def test_my_new_handler_sets_field():
    # Arrange
    state = await EditorState.create()
    assert state.my_field == "initial"

    # Act
    await state.my_new_handler("new_value")

    # Assert
    assert state.my_field == "new_value"
```

Run to confirm new tests pass:

```bash
uv run pytest tests/ -x -q -k "test_my_new_handler"
```