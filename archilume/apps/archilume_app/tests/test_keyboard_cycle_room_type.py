"""Tests for the keyboard-cycle-room-type feature.

Covers:
    * cycle_room_type pure state transitions (single, multi, wrap, out-of-range,
      unknown-type fallback).
    * The new 'c' key branch in handle_key that routes to cycle_room_type.

Reflex state is instantiated via ``object.__new__`` to skip the runtime token
plumbing in ``rx.State.__init__``. Side-effect helpers (_push_undo, _auto_save,
_recompute_df) are stubbed to keep tests hermetic — their behaviour has its own
coverage elsewhere.
"""

from __future__ import annotations

import pytest

from archilume_app.state.editor_state import EditorState


def _make_state(rooms: list[dict], selected: int = -1, multi: list[int] | None = None) -> EditorState:
    """Build an EditorState bypassing rx.State.__init__, seeded for cycle tests."""
    state = object.__new__(EditorState)
    object.__setattr__(state, "dirty_vars", set())
    object.__setattr__(state, "_self_dirty_computed_vars", set())
    object.__setattr__(state, "base_state", state)
    object.__setattr__(state, "_undo_stack", [])
    object.__setattr__(state, "_auto_save", lambda: None)
    object.__setattr__(state, "_recompute_df", lambda: None)
    object.__setattr__(state, "_push_undo", lambda entry: state._undo_stack.append(entry))
    object.__setattr__(state, "debug_mode", False)
    object.__setattr__(state, "_last_d_press", 0.0)

    state.rooms = rooms
    state.selected_room_idx = selected
    state.multi_selected_idxs = multi or []
    state.room_type_input = rooms[selected].get("room_type", "NONE") if 0 <= selected < len(rooms) else ""
    return state


def _room(name: str, rtype: str = "NONE") -> dict:
    return {"name": name, "parent": "", "room_type": rtype, "hdr_file": "h.hdr"}


@pytest.fixture
def single_room_state() -> EditorState:
    return _make_state([_room("R1", "NONE")], selected=0)


@pytest.fixture
def multi_room_state() -> EditorState:
    return _make_state(
        [_room("R1", "NONE"), _room("R2", "BED"), _room("R3", "LIVING")],
        selected=0,
        multi=[0, 1],
    )


# ---------------------------------------------------------------- cycle_room_type


def test_cycle_single_advances_none_to_bed(single_room_state: EditorState) -> None:
    EditorState.cycle_room_type.fn(single_room_state, 0)
    assert single_room_state.rooms[0]["room_type"] == "BED"
    assert single_room_state.room_type_input == "BED"


def test_cycle_advances_through_whole_cycle() -> None:
    expected = ["BED", "LIVING", "NON-RESI", "CIRC", "NONE"]
    state = _make_state([_room("R", "NONE")], selected=0)
    for want in expected:
        EditorState.cycle_room_type.fn(state, 0)
        assert state.rooms[0]["room_type"] == want


def test_cycle_wraps_circ_to_none() -> None:
    state = _make_state([_room("R", "CIRC")], selected=0)
    EditorState.cycle_room_type.fn(state, 0)
    assert state.rooms[0]["room_type"] == "NONE"


def test_cycle_multi_advances_all_selected(multi_room_state: EditorState) -> None:
    EditorState.cycle_room_type.fn(multi_room_state, 0)
    # Cycle is driven by rooms[0]'s type (NONE → BED). Both affected rooms are
    # set to the same next_type ("BED"). R3 at idx 2 is not in multi, unchanged.
    assert multi_room_state.rooms[0]["room_type"] == "BED"
    assert multi_room_state.rooms[1]["room_type"] == "BED"
    assert multi_room_state.rooms[2]["room_type"] == "LIVING"


def test_cycle_out_of_range_is_noop() -> None:
    state = _make_state([_room("R", "NONE")], selected=0)
    EditorState.cycle_room_type.fn(state, 99)
    assert state.rooms[0]["room_type"] == "NONE"


def test_cycle_unknown_type_falls_back_to_start() -> None:
    state = _make_state([_room("R", "WEIRD-VALUE")], selected=0)
    EditorState.cycle_room_type.fn(state, 0)
    assert state.rooms[0]["room_type"] == "NONE"


def test_cycle_records_undo_entry(single_room_state: EditorState) -> None:
    EditorState.cycle_room_type.fn(single_room_state, 0)
    assert len(single_room_state._undo_stack) == 1
    entry = single_room_state._undo_stack[0]
    assert entry["action"] == "room_type"
    assert entry["before"]["changes"][0]["room_type"] == "NONE"
    assert entry["after"]["changes"][0]["room_type"] == "BED"


# ---------------------------------------------------------------- handle_key 'c'


def _run_handle_key(state: EditorState, key: str) -> None:
    """Drain the handle_key generator. Side effects mutate state in place."""
    result = EditorState.handle_key.fn(state, key)
    if result is not None:
        list(result)


def test_handle_key_c_cycles_selected_room(single_room_state: EditorState) -> None:
    _run_handle_key(single_room_state, "c")
    assert single_room_state.rooms[0]["room_type"] == "BED"


def test_handle_key_c_respects_multi_selection(multi_room_state: EditorState) -> None:
    _run_handle_key(multi_room_state, "c")
    assert multi_room_state.rooms[0]["room_type"] == "BED"
    assert multi_room_state.rooms[1]["room_type"] == "BED"


def test_handle_key_c_with_no_selection_is_noop() -> None:
    state = _make_state([_room("R", "NONE")], selected=-1)
    _run_handle_key(state, "c")
    assert state.rooms[0]["room_type"] == "NONE"


def test_handle_key_c_uppercase_still_cycles(single_room_state: EditorState) -> None:
    # handle_key lowercases single-char keys before dispatch.
    _run_handle_key(single_room_state, "C")
    assert single_room_state.rooms[0]["room_type"] == "BED"
