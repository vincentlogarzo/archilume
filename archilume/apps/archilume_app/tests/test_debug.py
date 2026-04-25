"""Tests for :mod:`archilume_app.lib.debug`.

Covers correlation IDs, tiered ``debug_handler``, dynamic field discovery,
the async-flushing ``DebugTrace`` ring buffer with archive overflow, the
``auto_debug_instrument`` class decorator, and ``log_event``.

The module installs a global file handler at import time. We do not interfere
with that — tests run regardless of whether the file handler succeeded.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from archilume_app.lib import debug as dbg


# =========================================================================
# Tier fixture — every test that exercises the decorator restores the tier
# =========================================================================


@pytest.fixture
def tier(monkeypatch):
    """Return a setter that flips DEBUG_TIER for the test, then restores."""
    original = dbg.DEBUG_TIER

    def _set(value):
        dbg.DEBUG_TIER = value

    yield _set
    dbg.DEBUG_TIER = original


# =========================================================================
# new_correlation_id
# =========================================================================


class TestNewCorrelationId:
    def test_returns_string(self):
        assert isinstance(dbg.new_correlation_id(), str)

    def test_default_length_8(self):
        assert len(dbg.new_correlation_id()) == 8

    def test_collisions_are_rare(self):
        ids = {dbg.new_correlation_id() for _ in range(200)}
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
# set_debug_tier
# =========================================================================


class TestSetDebugTier:
    def test_accepts_valid_tiers(self, tier):
        for value in ("off", "light", "verbose"):
            dbg.set_debug_tier(value)
            assert dbg.DEBUG_TIER == value

    def test_rejects_unknown(self, tier):
        dbg.set_debug_tier("light")
        dbg.set_debug_tier("nonsense")  # no-op
        assert dbg.DEBUG_TIER == "light"


# =========================================================================
# Dynamic field discovery
# =========================================================================


class TestSnapshot:
    def test_captures_simplenamespace_fields(self):
        # SimpleNamespace doesn't have class-level annotations — discovery
        # walks the instance dict.
        state = SimpleNamespace(draw_mode="line", edit_mode=False, count=3)
        snap = dbg._snapshot(state)
        assert snap == {"draw_mode": "line", "edit_mode": False, "count": 3}

    def test_skips_private_underscore(self):
        state = SimpleNamespace(public_field=1, _private=2, __dunder__=3)
        snap = dbg._snapshot(state)
        assert snap == {"public_field": 1}

    def test_skips_untracked_fields(self):
        state = SimpleNamespace(draw_mode="ok", router="reflex internal", debug_log=[])
        snap = dbg._snapshot(state)
        assert "draw_mode" in snap
        assert "router" not in snap
        assert "debug_log" not in snap

    def test_lists_and_dicts_copied(self):
        verts = [[1, 2]]
        pts = {"a": 1}
        state = SimpleNamespace(draw_vertices=verts, divider_points=pts)
        snap = dbg._snapshot(state)
        verts.append([3, 4])
        pts["b"] = 2
        assert snap["draw_vertices"] == [[1, 2]]
        assert snap["divider_points"] == {"a": 1}

    def test_skips_methods_and_properties(self):
        class S:
            x: int = 1

            @property
            def computed(self):
                return self.x * 2

            def event_handler(self):
                pass

        s = S()
        snap = dbg._snapshot(s)
        assert "x" in snap
        assert "computed" not in snap
        assert "event_handler" not in snap

    def test_per_class_cache_used(self):
        # First snapshot populates cache; second should hit it.
        class Cached:
            a: int = 1

        c = Cached()
        dbg._SNAPSHOT_FIELDS_CACHE.pop(Cached, None)
        dbg._snapshot(c)
        assert Cached in dbg._SNAPSHOT_FIELDS_CACHE


# =========================================================================
# _diff
# =========================================================================


class TestDiff:
    def test_no_changes_returns_empty(self):
        assert dbg._diff({"a": 1, "b": 2}, {"a": 1, "b": 2}) == {}

    def test_reports_changed_field(self):
        assert dbg._diff({"a": 1}, {"a": 2}) == {"a": [1, 2]}

    def test_ignores_new_fields_not_in_before(self):
        assert dbg._diff({"a": 1}, {"a": 1, "new": "x"}) == {}

    def test_summarizes_large_values(self):
        out = dbg._diff({"a": list(range(20))}, {"a": []})
        assert out["a"][0] == "list[20]"


# =========================================================================
# _summarize / _safe_repr
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
        assert dbg._safe_repr({key: "plaintext"})[key] == "***"

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
# debug_handler — tiered behaviour
# =========================================================================


class _FakeState(SimpleNamespace):
    pass


class TestDebugHandlerOff:
    def test_pass_through_zero_overhead(self, tier):
        tier("off")
        calls = []

        @dbg.debug_handler
        def handler(self, x):
            calls.append(x)
            return x * 2

        assert handler(_FakeState(), 5) == 10
        assert calls == [5]

    def test_generator_pass_through_off(self, tier):
        tier("off")

        @dbg.debug_handler
        def gen(self, n):
            yield from range(n)

        assert list(gen(_FakeState(), 3)) == [0, 1, 2]


class TestDebugHandlerLight:
    def test_records_minimal_entry(self, tier):
        tier("light")
        dbg.trace.clear()

        @dbg.debug_handler
        def handler(self, x):
            return x

        handler(_FakeState(draw_mode="x"), 1)
        recent = dbg.trace.get_recent(1)
        assert recent[0]["event"] == "handler"
        assert "elapsed_ms" in recent[0]
        # Light tier omits args and changes.
        assert "args" not in recent[0]
        assert "changes" not in recent[0]

    def test_does_not_call_snapshot(self, tier, monkeypatch):
        tier("light")
        snapshot_calls = []
        monkeypatch.setattr(dbg, "_snapshot", lambda s: snapshot_calls.append(s) or {})

        @dbg.debug_handler
        def handler(self, x):
            return x

        handler(_FakeState(), 1)
        assert snapshot_calls == []

    def test_generator_light(self, tier):
        tier("light")
        dbg.trace.clear()

        @dbg.debug_handler
        def gen(self):
            yield 1
            yield 2

        assert list(gen(_FakeState())) == [1, 2]
        assert dbg.trace.get_recent(1)[0]["event"] == "gen"


class TestDebugHandlerVerbose:
    def test_records_full_entry_with_changes(self, tier):
        tier("verbose")
        dbg.trace.clear()

        @dbg.debug_handler
        def handler(self, x):
            self.draw_mode = "poly"
            return x

        handler(_FakeState(draw_mode="line"), 1)
        recent = dbg.trace.get_recent(1)[0]
        assert recent["event"] == "handler"
        assert recent["args"] == [1]
        assert recent["changes"] == {"draw_mode": ["line", "poly"]}
        assert recent["elapsed_ms"] >= 0

    def test_no_changes_omits_changes_key(self, tier):
        tier("verbose")
        dbg.trace.clear()

        @dbg.debug_handler
        def handler(self):
            pass

        handler(_FakeState(draw_mode="line"))
        recent = dbg.trace.get_recent(1)[0]
        assert "changes" not in recent

    def test_generator_verbose_diffs_after_yield(self, tier):
        tier("verbose")
        dbg.trace.clear()

        @dbg.debug_handler
        def gen(self):
            yield 1
            self.draw_mode = "poly"
            yield 2

        list(gen(_FakeState(draw_mode="line")))
        recent = dbg.trace.get_recent(1)[0]
        assert recent["changes"] == {"draw_mode": ["line", "poly"]}


# =========================================================================
# auto_debug_instrument
# =========================================================================


class TestAutoDebugInstrument:
    def test_wraps_public_functions(self, tier):
        tier("light")
        dbg.trace.clear()

        @dbg.auto_debug_instrument()
        class S:
            def public(self):
                return "pub"

            def _private(self):
                return "priv"

        s = S()
        s.public()
        s._private()
        events = [e["event"] for e in dbg.trace.get_recent(10)]
        assert "public" in events
        assert "_private" not in events

    def test_respects_exclude(self, tier):
        tier("light")
        dbg.trace.clear()

        @dbg.auto_debug_instrument(exclude={"hot_path"})
        class S:
            def hot_path(self):
                return 1

            def normal(self):
                return 2

        s = S()
        s.hot_path()
        s.normal()
        events = [e["event"] for e in dbg.trace.get_recent(10)]
        assert "hot_path" not in events
        assert "normal" in events

    def test_skips_properties(self, tier):
        tier("light")
        dbg.trace.clear()

        @dbg.auto_debug_instrument()
        class S:
            @property
            def computed(self):
                return 42

        # Should not blow up at decoration time, and accessing the prop
        # should not produce a trace entry.
        s = S()
        before = len(dbg.trace.entries)
        _ = s.computed
        after = len(dbg.trace.entries)
        assert after == before


# =========================================================================
# DebugTrace — async flush + archive
# =========================================================================


class TestDebugTrace:
    def test_add_appends_entry_with_rid(self):
        t = dbg.DebugTrace(max_entries=10)
        with dbg.with_correlation_id("rid_test"):
            t.add("evt")
        assert t.entries[0]["event"] == "evt"
        assert t.entries[0]["rid"] == "rid_test"

    def test_elapsed_ms_round_tripped(self):
        t = dbg.DebugTrace(max_entries=10)
        t.add("evt", elapsed_ms=1.234567)
        assert t.entries[0]["elapsed_ms"] == 1.235  # rounded to 3dp

    def test_ring_buffer_caps_length(self):
        t = dbg.DebugTrace(max_entries=3)
        for i in range(6):
            t.add(f"e{i}")
        assert len(t.entries) == 3
        events = [e["event"] for e in t.entries]
        assert events == ["e3", "e4", "e5"]

    def test_overflow_lands_in_archive(self, tmp_path):
        t = dbg.DebugTrace(max_entries=2)
        t.set_project_path(tmp_path)
        for i in range(5):
            t.add(f"e{i}")
        t.flush()  # synchronous, drains archive queue too
        archive = tmp_path / "debug_trace.archive.jsonl"
        assert archive.exists()
        lines = archive.read_text().strip().split("\n")
        evicted = [json.loads(l)["event"] for l in lines]
        assert evicted == ["e0", "e1", "e2"]  # 3 evicted as buffer cap=2

    def test_get_recent_returns_tail(self):
        t = dbg.DebugTrace()
        for i in range(5):
            t.add(f"e{i}")
        recent = t.get_recent(2)
        assert [e["event"] for e in recent] == ["e3", "e4"]

    def test_clear_empties_buffer(self):
        t = dbg.DebugTrace()
        t.add("x")
        t.clear()
        assert len(t.entries) == 0

    def test_flush_writes_json(self, tmp_path):
        t = dbg.DebugTrace()
        t.set_project_path(tmp_path)
        t.add("evt")
        t.flush()
        p = tmp_path / "debug_trace.json"
        assert p.exists()
        assert json.loads(p.read_text())[0]["event"] == "evt"

    def test_flush_noop_when_empty(self, tmp_path):
        t = dbg.DebugTrace()
        t.set_project_path(tmp_path)
        t.flush()
        assert not (tmp_path / "debug_trace.json").exists()

    def test_async_writer_eventually_flushes(self, tmp_path):
        t = dbg.DebugTrace()
        t.set_project_path(tmp_path)
        for i in range(60):  # over the batch threshold of 50
            t.add(f"e{i}")
        # The writer thread runs every 500ms — wait up to 1.5s
        deadline = time.monotonic() + 1.5
        target = tmp_path / "debug_trace.json"
        while time.monotonic() < deadline:
            if target.exists():
                break
            time.sleep(0.05)
        assert target.exists()


# =========================================================================
# relocate_to_project
# =========================================================================


class TestRelocateToProject:
    def test_creates_logs_subdir(self, tmp_path):
        dbg.relocate_to_project(tmp_path)
        assert (tmp_path / "logs").is_dir()

    def test_log_file_lands_in_project(self, tmp_path, tier):
        tier("verbose")
        dbg.relocate_to_project(tmp_path)
        dbg.logger.error("relocation_test_marker")
        # File handler buffers — trigger flush by closing.
        for h in list(dbg.logger.handlers):
            if hasattr(h, "flush"):
                h.flush()
        log_file = tmp_path / "logs" / "archilume_app.log"
        assert log_file.exists()
        assert "relocation_test_marker" in log_file.read_text(encoding="utf-8")

    def test_trace_lands_in_logs_subdir(self, tmp_path, tier):
        tier("light")
        dbg.relocate_to_project(tmp_path)
        dbg.trace.add("post_relocate_event")
        dbg.trace.flush()
        trace_file = tmp_path / "logs" / "debug_trace.json"
        assert trace_file.exists()

    def test_idempotent_for_same_project(self, tmp_path):
        first = dbg.relocate_to_project(tmp_path)
        second = dbg.relocate_to_project(tmp_path)
        assert first == second == tmp_path / "logs"

    def test_returns_logs_dir(self, tmp_path):
        result = dbg.relocate_to_project(tmp_path)
        assert result == tmp_path / "logs"


# =========================================================================
# log_event
# =========================================================================


class TestLogEvent:
    def test_off_tier_silent(self, tier):
        tier("off")
        dbg.trace.clear()
        dbg.log_event("noop_tag", x=1)
        assert len(dbg.trace.entries) == 0

    def test_light_queues_trace_entry(self, tier):
        tier("light")
        dbg.trace.clear()
        dbg.log_event("light_tag", x=1)
        recent = dbg.trace.get_recent(1)[0]
        assert recent["event"] == "light_tag"
        assert recent["args"] == {"x": 1}

    def test_redacts_sensitive_in_args(self, tier):
        tier("light")
        dbg.trace.clear()
        dbg.log_event("auth", api_key="hunter2", user="alice")
        recent = dbg.trace.get_recent(1)[0]
        assert recent["args"]["api_key"] == "***"
        assert recent["args"]["user"] == "alice"
