from typing import Protocol


class StoreError(Exception):
    """A store failed; the core turns it into a 503."""


class Store(Protocol):
    """Link storage every deployment implements; one contract suite covers it."""

    def create_if_absent(self, code: str, url: str) -> bool:
        """Store a link unless the code is taken.

        Args:
            code: Short code.
            url: Target URL.

        Returns:
            True if created, False if the code already existed (nothing changes).

        Raises:
            StoreError: The store failed.
        """
        ...

    def get(self, code: str) -> str | None:
        """Look a code up.

        Args:
            code: Short code.

        Returns:
            The URL, or None if unknown.

        Raises:
            StoreError: The store failed.
        """
        ...

    def trim(self, keep: int, trigger: int) -> int:
        """Delete the oldest links once enough have piled up.

        Args:
            keep: Number of newest links that must remain.
            trigger: Link count at which trimming starts; below it nothing happens.

        Returns:
            Number of links deleted.

        Raises:
            StoreError: The store failed.
        """
        ...
