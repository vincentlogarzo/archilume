"""Tests for :mod:`archilume_app.lib.debug`.

Covers the 7 public callables: ``new_correlation_id``, ``with_correlation_id``,
``debug_handler``, ``_snapshot``, ``_diff``, ``_summarize``, ``_safe_repr``,
plus smoke coverage for the ``DebugTrace`` ring buffer.

The module installs a global file handler at import time. We do not interfere
with that — tests run regardless of whether the file handler succeeded.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from archilume_app.lib import debug as dbg


# =========================================================================
# new_correlation_id
# =========================================================================


class TestNewCorrelationId:
    def test_returns_string(self):
        rid = dbg.new_correlation_id()
        assert isinstance(rid, str)

    def test_default_length_8(self):
        assert len(dbg.new_correlation_id()) == 8

    def test_collisions_are_rare(self):
        ids = {dbg.new_correlation_id() for _ in range(200)}
        # 8 hex chars = 2^32 space — 200 ids colliding is astronomically unlikely.
        assert len(ids) == 200


# =========================================================================
# with_correlation_id
# =========================================================================


class TestWithCorrelationId:
    def test_default_sets_random_id(self):
        with dbg.with_correlation_id() as rid:
            assert dbg.correlation_id.get() == rid
            assert len(rid) == 8

    def test_explicit_id_honoured(self):
        with dbg.with_correlation_id("abc123") as rid:
            assert rid == "abc123"
            assert dbg.correlation_id.get() == "abc123"

    def test_resets_after_block(self):
        previous = dbg.correlation_id.get()
        with dbg.with_correlation_id("tmpid"):
            assert dbg.correlation_id.get() == "tmpid"
        assert dbg.correlation_id.get() == previous

    def test_resets_even_on_exception(self):
        previous = dbg.correlation_id.get()
        with pytest.raises(RuntimeError):
            with dbg.with_correlation_id("xyz"):
                raise RuntimeError("boom")
        assert dbg.correlation_id.get() == previous

    def test_nested_ids_restore(self):
        with dbg.with_correlation_id("outer"):
            with dbg.with_correlation_id("inner"):
                assert dbg.correlation_id.get() == "inner"
            assert dbg.correlation_id.get() == "outer"


# =========================================================================
# _snapshot
# =========================================================================


class TestSnapshot:
    def test_captures_tracked_fields(self):
        state = SimpleNamespace(
            draw_mode="line", edit_mode=False,
            selected_room_idx=3,
            unrelated_field="ignored",
        )
        snap = dbg._snapshot(state)
        assert snap["draw_mode"] == "line"
        assert snap["edit_mode"] is False
        assert snap["selected_room_idx"] == 3
        assert "unrelated_field" not in snap

    def test_missing_fields_omitted(self):
        state = SimpleNamespace(draw_mode="x")
        snap = dbg._snapshot(state)
        assert snap == {"draw_mode": "x"}

    def test_lists_and_dicts_copied(self):
        verts = [[1, 2]]
        pts = {"a": 1}
        state = SimpleNamespace(draw_vertices=verts, divider_points=pts)
        snap = dbg._snapshot(state)
        verts.append([3, 4])
        pts["b"] = 2
        # Snapshot must not reflect post-snapshot mutation.
        assert snap["draw_vertices"] == [[1, 2]]
        assert snap["divider_points"] == {"a": 1}


# =========================================================================
# _diff
# =========================================================================


class TestDiff:
    def test_no_changes_returns_empty(self):
        before = {"a": 1, "b": 2}
        assert dbg._diff(before, {"a": 1, "b": 2}) == {}

    def test_reports_changed_field(self):
        assert dbg._diff({"a": 1}, {"a": 2}) == {"a": [1, 2]}

    def test_ignores_new_fields_not_in_before(self):
        # Diff walks `before`'s keys; new keys in `after` don't appear.
        assert dbg._diff({"a": 1}, {"a": 1, "new": "x"}) == {}

    def test_summarizes_large_values(self):
        big_list = list(range(20))
        out = dbg._diff({"a": big_list}, {"a": []})
        assert out["a"][0] == "list[20]"


# =========================================================================
# _summarize
# =========================================================================


class TestSummarize:
    def test_short_list_preserved(self):
        assert dbg._summarize([1, 2, 3]) == [1, 2, 3]

    def test_long_list_truncated_to_tag(self):
        assert dbg._summarize(list(range(10))) == "list[10]"

    def test_short_dict_preserved(self):
        assert dbg._summarize({"a": 1}) == {"a": 1}

    def test_long_dict_truncated(self):
        assert dbg._summarize({str(i): i for i in range(10)}) == "dict[10 keys]"

    def test_scalar_passthrough(self):
        assert dbg._summarize("x") == "x"
        assert dbg._summarize(42) == 42


# =========================================================================
# _safe_repr
# =========================================================================


class TestSafeRepr:
    def test_scalar_types_passthrough(self):
        assert dbg._safe_repr(1) == 1
        assert dbg._safe_repr(1.5) == 1.5
        assert dbg._safe_repr(True) is True
        assert dbg._safe_repr(None) is None
        assert dbg._safe_repr("hi") == "hi"

    def test_tuples_become_lists(self):
        assert dbg._safe_repr((1, 2, 3)) == [1, 2, 3]

    def test_nested_dict(self):
        assert dbg._safe_repr({"a": [1, 2]}) == {"a": [1, 2]}

    @pytest.mark.parametrize("key", [
        "password", "Password", "api_key", "API_KEY", "apikey",
        "secret", "access_token", "Authorization", "bearer",
        "private_key", "credential", "CREDENTIALS",
    ])
    def test_redacts_sensitive_keys(self, key):
        out = dbg._safe_repr({key: "plaintext-should-not-leak"})
        assert out[key] == "***"

    def test_does_not_redact_safe_keys(self):
        assert dbg._safe_repr({"username": "u"}) == {"username": "u"}

    def test_long_object_repr_truncated(self):
        class Custom:
            def __str__(self):
                return "x" * 500

        out = dbg._safe_repr(Custom())
        assert isinstance(out, str)
        assert len(out) == 120


# =========================================================================
# debug_handler decorator — regular + generator
# =========================================================================


class _FakeState(SimpleNamespace):
    """Mimics the Reflex state surface debug_handler introspects."""


class TestDebugHandler:
    def test_passes_through_when_debug_disabled(self):
        calls = []

        @dbg.debug_handler
        def handler(self, x):
            calls.append(x)
            return x * 2

        state = _FakeState(debug_mode=False, draw_mode="line")
        assert handler(state, 5) == 10
        assert calls == [5]

    def test_runs_when_debug_enabled(self):
        @dbg.debug_handler
        def handler(self, x):
            self.draw_mode = "poly"
            return x

        state = _FakeState(debug_mode=True, draw_mode="line")
        handler(state, 1)
        assert state.draw_mode == "poly"

    def test_generator_handler_passes_through_when_disabled(self):
        @dbg.debug_handler
        def gen_handler(self, n):
            for i in range(n):
                yield i

        state = _FakeState(debug_mode=False, draw_mode="x")
        assert list(gen_handler(state, 3)) == [0, 1, 2]

    def test_generator_handler_runs_when_enabled(self):
        @dbg.debug_handler
        def gen_handler(self):
            yield 1
            self.draw_mode = "poly"
            yield 2

        state = _FakeState(debug_mode=True, draw_mode="line")
        results = list(gen_handler(state))
        assert results == [1, 2]
        assert state.draw_mode == "poly"


# =========================================================================
# DebugTrace ring buffer — bonus coverage
# =========================================================================


class TestDebugTrace:
    def test_add_appends_entry(self):
        trace = dbg.DebugTrace(max_entries=10)
        trace.add("test_event", args=(1, 2))
        assert len(trace.entries) == 1
        assert trace.entries[0]["event"] == "test_event"

    def test_ring_buffer_caps_length(self):
        trace = dbg.DebugTrace(max_entries=3)
        for i in range(6):
            trace.add(f"e{i}")
        assert len(trace.entries) == 3
        assert trace.entries[0]["event"] == "e3"

    def test_get_recent_returns_tail(self):
        trace = dbg.DebugTrace()
        for i in range(5):
            trace.add(f"e{i}")
        recent = trace.get_recent(2)
        assert len(recent) == 2
        assert recent[-1]["event"] == "e4"

    def test_clear_empties_buffer(self):
        trace = dbg.DebugTrace()
        trace.add("x")
        trace.clear()
        assert trace.entries == []

    def test_flush_writes_json(self, tmp_path):
        trace = dbg.DebugTrace()
        trace.set_project_path(tmp_path)
        trace.add("evt")
        trace.flush()
        p = tmp_path / "debug_trace.json"
        assert p.exists()
        assert json.loads(p.read_text())[0]["event"] == "evt"

    def test_flush_noop_when_empty(self, tmp_path):
        trace = dbg.DebugTrace()
        trace.set_project_path(tmp_path)
        trace.flush()
        assert not (tmp_path / "debug_trace.json").exists()
