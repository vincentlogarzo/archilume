"""Performance budget for ``debug_handler``.

These tests assert that default-on tracing has a bounded per-call cost:

- ``light`` tier: < 5 µs of overhead vs an undecorated baseline.
- ``verbose`` tier: < 100 µs for a state with ~100 trackable fields.

If a test fails, either the implementation regressed or the calling handler
should be added to ``editor_state._DEBUG_EXCLUDE``.

Marked ``perf`` so they can be selectively skipped on noisy CI runners with
``-m "not perf"``. The thresholds carry slack vs cold timings to absorb
GC pauses, but should still catch order-of-magnitude regressions.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from archilume_app.lib import debug as dbg


pytestmark = pytest.mark.perf


@pytest.fixture
def tier():
    original = dbg.DEBUG_TIER

    def _set(value):
        dbg.DEBUG_TIER = value

    yield _set
    dbg.DEBUG_TIER = original


def _bench(fn, *, iters: int = 5000) -> float:
    """Return per-call mean overhead in microseconds."""
    # Warm up — first call may JIT-prime the deque, file handles, etc.
    for _ in range(50):
        fn()
    t0 = time.perf_counter()
    for _ in range(iters):
        fn()
    elapsed_s = time.perf_counter() - t0
    return (elapsed_s / iters) * 1_000_000  # → µs


def _make_wide_state(n_fields: int = 100) -> SimpleNamespace:
    return SimpleNamespace(**{f"field_{i}": i for i in range(n_fields)})


class TestLightTierOverhead:
    def test_under_5us_per_call(self, tier):
        tier("light")
        dbg.trace.clear()

        @dbg.debug_handler
        def decorated(self, x):
            return x

        def undecorated(self, x):
            return x

        state = _make_wide_state(100)
        decorated_us = _bench(lambda: decorated(state, 1))
        baseline_us = _bench(lambda: undecorated(state, 1))
        overhead = decorated_us - baseline_us
        assert overhead < 5.0, (
            f"light-tier overhead {overhead:.2f}µs/call exceeds 5µs budget "
            f"(decorated={decorated_us:.2f}, baseline={baseline_us:.2f})"
        )


class TestVerboseTierOverhead:
    def test_under_100us_per_call_for_100_fields(self, tier):
        tier("verbose")
        dbg.trace.clear()

        @dbg.debug_handler
        def decorated(self, x):
            return x

        def undecorated(self, x):
            return x

        state = _make_wide_state(100)
        decorated_us = _bench(lambda: decorated(state, 1), iters=2000)
        baseline_us = _bench(lambda: undecorated(state, 1), iters=2000)
        overhead = decorated_us - baseline_us
        assert overhead < 100.0, (
            f"verbose-tier overhead {overhead:.2f}µs/call exceeds 100µs budget "
            f"(decorated={decorated_us:.2f}, baseline={baseline_us:.2f})"
        )


class TestOffTierOverhead:
    def test_near_zero_when_disabled(self, tier):
        tier("off")

        @dbg.debug_handler
        def decorated(self, x):
            return x

        state = _make_wide_state(10)
        # Off tier should be a single global read + call-through.
        per_call_us = _bench(lambda: decorated(state, 1))
        assert per_call_us < 5.0, f"off-tier per-call cost {per_call_us:.2f}µs"


class TestTraceAddNonBlocking:
    def test_put_does_not_block(self):
        t = dbg.DebugTrace(max_entries=1000)
        # Saturate the buffer so every add evicts (worst case for archive queue).
        for i in range(1500):
            t.add(f"e{i}")
        # 1000 adds should be near-instant — well under 50ms.
        t0 = time.perf_counter()
        for i in range(1000):
            t.add(f"x{i}")
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert elapsed_ms < 50, f"1000 adds took {elapsed_ms:.1f}ms"
