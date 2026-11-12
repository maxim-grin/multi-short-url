from typing import Protocol

KEEP = 1000
TRIGGER = 1100


class StoreError(Exception):
    pass


class Store(Protocol):
    def create_if_absent(self, code: str, url: str) -> bool: ...

    def get(self, code: str) -> str | None: ...

    def trim(self, keep: int, trigger: int) -> int:
        """At `trigger` or more links, delete the oldest so `keep` remain."""
        ...
