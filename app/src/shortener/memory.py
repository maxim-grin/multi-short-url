import threading


class MemoryStore:
    def __init__(self) -> None:
        self._links: dict[str, str] = {}  # insertion order is age order
        self._lock = threading.Lock()

    def create_if_absent(self, code: str, url: str) -> bool:
        with self._lock:
            if code in self._links:
                return False
            self._links[code] = url
            return True

    def get(self, code: str) -> str | None:
        with self._lock:
            return self._links.get(code)

    def trim(self, keep: int, trigger: int) -> int:
        with self._lock:
            if len(self._links) < trigger:
                return 0
            old = list(self._links)[: max(len(self._links) - keep, 0)]
            for code in old:
                del self._links[code]
            return len(old)
