from concurrent.futures import ThreadPoolExecutor

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
