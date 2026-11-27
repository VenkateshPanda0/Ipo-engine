"""The in-process limiter must not remember every client it has ever seen."""

from __future__ import annotations

from unittest.mock import patch

from ipo_engine.screening.services.documents import RateLimiter


def test_idle_keys_are_dropped_so_memory_stays_bounded() -> None:
    limiter = RateLimiter(5)
    clock = [1000.0]
    with patch("ipo_engine.screening.services.documents.time.monotonic", lambda: clock[0]):
        for i in range(RateLimiter.PRUNE_EVERY - 1):
            assert limiter.allow(f"client-{i}")
        assert len(limiter._hits) == RateLimiter.PRUNE_EVERY - 1
        clock[0] += 120  # every window has passed
        limiter.allow("one-more")  # the call that triggers the clean-up
    assert len(limiter._hits) == 1


def test_the_limit_itself_is_unchanged() -> None:
    limiter = RateLimiter(3)
    assert [limiter.allow("a") for _ in range(5)] == [True, True, True, False, False]
    assert limiter.allow("b")
