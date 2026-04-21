# Feature: keyboard-cycle-room-type

## Spec

Add a keyboard shortcut (`c`) that cycles the room type of the currently
selected room (or all multi-selected rooms), reusing the existing
`EditorState.cycle_room_type` event handler. Must route through the existing
`handle_key_event` → `_handle_key_event_body` → `handle_key` dispatch chain so
correlation-ID tracing still works. Click-to-cycle badge in `project_tree.py`
must remain unchanged.

## Target files

- `archilume/apps/archilume_app/archilume_app/state/editor_state.py` — add one
  `elif k == "c":` branch inside `handle_key` (around line 6100, adjacent to
  the `t` image-variant branch).

## Test file

- `archilume/apps/archilume_app/tests/test_keyboard_cycle_room_type.py`

## Status

- [x] Explore done (Phase 1 exploration covered this ground — see plan)
- [x] Tests scaffolded
- [x] Tests committed (`cf6d652`)
- [x] Implementation edit (uncommitted — review before committing)
- [x] Tests passing (11/11)
- [x] Audit ≥ 9/10

## Audit 1 (10/10 — ship it)

```
SCORE: 10/10
PASS: 1=N/A(1), 2=P(2), 3=P(1), 4=P(1), 5=P(1), 6=N/A(1), 7=P(1), 8=P(2)
GAPS:
- none — new 'c' branch mirrors the 't' branch (plain call, no yield),
  correctly reuses cycle_room_type which already handles _push_undo /
  _auto_save / _recompute_df
- none — routing stays inside handle_key (single-key unmodified action),
  preserving handle_key_event → _handle_key_event_body → handle_key chain
  and correlation-ID tracing
- none — 4 handle_key('c') tests plus 6 cycle_room_type unit tests cover
  single/multi/no-selection/uppercase/wrap/out-of-range/undo
NEXT_EDIT: none — ship it
```

Note: the audit's PASS tally is one point off in its own weighting (cat 8 is
1 pt, cat 1 N/A at 1 pt gives max 9). Either reading clears the 9/10 gate;
recalibrate category weights after the next audit run.

## Test invocation

```bash
uv run pytest archilume/apps/archilume_app/tests/test_keyboard_cycle_room_type.py
```
