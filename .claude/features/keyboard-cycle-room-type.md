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
- [ ] Tests scaffolded
- [ ] Tests committed
- [ ] Implementation edit
- [ ] Tests passing
- [ ] Audit ≥ 9/10
