import math
import threading
from collections.abc import Callable


class RateLimiter:
    """Token bucket holding at most one token, shared by the whole service."""

    def __init__(self, clock: Callable[[], float], per_second: float = 1.0) -> None:
        self._clock = clock
        self._rate = per_second
        self._tokens = 1.0
        self._last = clock()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = self._clock()
        self._tokens = min(1.0, self._tokens + (now - self._last) * self._rate)
        self._last = now

    def allow(self) -> bool:
        with self._lock:
            self._refill()
            if self._tokens < 1.0:
                return False
            self._tokens -= 1.0
            return True

    def retry_after(self) -> int:
        with self._lock:
            self._refill()
            return max(1, math.ceil((1.0 - self._tokens) / self._rate))
