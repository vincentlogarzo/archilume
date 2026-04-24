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

The app must be running. If it is not:

```bash
ARCHILUME_DEBUG=1 python examples/launch_archilume_app.py --ensure
```

Then exercise the feature in the browser before running this skill.

---

## Step 1 — Read the log tail

Read the last 100 lines of the app log:

```bash
tail -n 100 "$USERPROFILE/.archilume/logs/archilume_app.log"
```

Or on Linux/Mac:

```bash
tail -n 100 ~/.archilume/logs/archilume_app.log
```

**Look for:**

- Any `[ERROR]` or `[CRITICAL]` lines that appeared after the change
- Tracebacks (`Traceback (most recent call last)`) referencing modified files
- The expected event handler name appearing with `[DEBUG]` level entries
- Missing events that should have fired (absence of expected log lines)
- `[rid=XXXXXXXX]` correlation IDs — if an error appears, grep the same rid to trace the full chain

**Flag if:** Any new ERROR/CRITICAL lines, any traceback referencing the changed file.

---

## Step 2 — Read the debug trace

Read the structured state-diff ring buffer (last 200 state transitions):

```
Read: C:\Users\{username}\.archilume\logs\debug_trace.json
```

Or after a project is loaded, the trace moves to `{project_dir}/debug_trace.json`.

Each entry has:
- `ts` — timestamp
- `event` — event handler name that fired
- `args` — call arguments (redacted)
- `changes` — dict of `field_name: [before_value, after_value]`

**Verify:**

- The expected event handler name appears in recent entries (sorted by `ts`)
- State fields changed to the expected values (`before → after`)
- No unexpected fields were mutated by the change
- Event sequence is correct (for multi-step flows, check ordering by `ts`)

**Flag if:** Expected event is absent, wrong fields changed, unexpected mutations.

---

## Step 3 — Ask user to check browser console

Say to the user:

> "Please check the browser DevTools console (F12 → Console tab) and paste any red errors or warnings that appeared after you tested the feature."

If the user reports errors:
- `TypeError` or `ReferenceError` — JS-level bug, likely in a component prop or event binding
- `WebSocket closed` — backend crashed mid-session; check log for traceback
- Reflex `hydration` warnings — state shape mismatch between server and client; likely a computed var or state field type issue
- No errors — proceed

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