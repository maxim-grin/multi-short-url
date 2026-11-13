from concurrent.futures import ThreadPoolExecutor

import pytest

from shortener.limiter import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_first_allowed_second_denied():
    clock = FakeClock()
    limiter = RateLimiter(clock)
    assert limiter.allow()
    assert not limiter.allow()


def test_refills_after_one_second():
    clock = FakeClock()
    limiter = RateLimiter(clock)
    limiter.allow()
    clock.now += 0.5
    assert not limiter.allow()
    clock.now += 0.5
    assert limiter.allow()


def test_retry_after_is_one_after_denial():
    clock = FakeClock()
    limiter = RateLimiter(clock)
    limiter.allow()
    assert not limiter.allow()
    assert limiter.retry_after() == 1


def test_idle_time_does_not_bank_tokens():
    clock = FakeClock()
    limiter = RateLimiter(clock)
    clock.now += 60
    assert limiter.allow()
    assert not limiter.allow()


def test_concurrent_allow_gives_exactly_one():
    limiter = RateLimiter(FakeClock())
    with ThreadPoolExecutor(50) as pool:
        results = list(pool.map(lambda _: limiter.allow(), range(50)))
    assert results.count(True) == 1


def test_clock_stepping_back_does_not_go_negative():
    clock = FakeClock()
    limiter = RateLimiter(clock)
    assert limiter.allow()
    clock.now -= 10
    assert not limiter.allow()
    clock.now += 1
    assert limiter.allow()


def test_retry_after_on_fresh_limiter_is_one():
    assert RateLimiter(FakeClock()).retry_after() == 1


def test_rejects_non_positive_rate():
    for bad in (0, -1.0):
        with pytest.raises(ValueError, match="positive"):
            RateLimiter(FakeClock(), per_second=bad)
