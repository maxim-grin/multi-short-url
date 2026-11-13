import math
import threading
from collections.abc import Callable


class RateLimiter:
    """Token bucket holding at most one token, shared by the whole service.

    Attributes:
        _clock: Returns seconds; a backwards step adds no tokens.
        _rate: Tokens added per second.
        _tokens: Tokens now available, 0 to 1.
        _last: Clock reading at the last refill.
    """

    def __init__(self, clock: Callable[[], float], per_second: float = 1.0) -> None:
        """Start with one token.

        Args:
            clock: Returns the current time in seconds, injected for tests.
            per_second: Tokens added per second.

        Raises:
            ValueError: per_second is not positive.
        """
        if per_second <= 0:
            raise ValueError("per_second must be positive")
        self._clock = clock
        self._rate = per_second
        self._tokens = 1.0
        self._last = clock()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        """Add tokens for the time since the last call; caller holds the lock."""
        now = self._clock()
        self._tokens = min(1.0, self._tokens + max(0.0, now - self._last) * self._rate)
        self._last = now

    def allow(self) -> bool:
        """Take a token if one is available.

        Returns:
            True if the caller may proceed.
        """
        with self._lock:
            self._refill()
            if self._tokens < 1.0:
                return False
            self._tokens -= 1.0
            return True

    def retry_after(self) -> int:
        """Return whole seconds until a token is available, at least 1."""
        with self._lock:
            self._refill()
            return max(1, math.ceil((1.0 - self._tokens) / self._rate))
