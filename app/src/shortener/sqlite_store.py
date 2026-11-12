import sqlite3
import threading

from shortener.store import StoreError


class SqliteStore:
    def __init__(self, path: str) -> None:
        self._lock = threading.Lock()
        try:
            # One connection shared across threads; the lock serialises use.
            self._db = sqlite3.connect(path, check_same_thread=False)
            with self._db:
                self._db.execute(
                    "CREATE TABLE IF NOT EXISTS links ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "code TEXT NOT NULL UNIQUE, url TEXT NOT NULL)"
                )
        except sqlite3.Error as e:
            raise StoreError(str(e)) from e

    def create_if_absent(self, code: str, url: str) -> bool:
        try:
            with self._lock, self._db:
                cur = self._db.execute(
                    "INSERT OR IGNORE INTO links (code, url) VALUES (?, ?)",
                    (code, url),
                )
                return cur.rowcount == 1
        except sqlite3.Error as e:
            raise StoreError(str(e)) from e

    def get(self, code: str) -> str | None:
        try:
            with self._lock:
                row = self._db.execute(
                    "SELECT url FROM links WHERE code = ?", (code,)
                ).fetchone()
            return row[0] if row else None
        except sqlite3.Error as e:
            raise StoreError(str(e)) from e

    def trim(self, keep: int, trigger: int) -> int:
        try:
            with self._lock, self._db:
                (n,) = self._db.execute("SELECT COUNT(*) FROM links").fetchone()
                if n < trigger:
                    return 0
                cur = self._db.execute(
                    "DELETE FROM links WHERE id NOT IN "
                    "(SELECT id FROM links ORDER BY id DESC LIMIT ?)",
                    (keep,),
                )
                return cur.rowcount
        except sqlite3.Error as e:
            raise StoreError(str(e)) from e

    def close(self) -> None:
        with self._lock:
            self._db.close()
