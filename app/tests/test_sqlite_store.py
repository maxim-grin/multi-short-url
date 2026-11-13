import threading

import pytest

from shortener.sqlite_store import SqliteStore
from shortener.store import StoreError


def test_links_survive_reopen(tmp_path):
    path = str(tmp_path / "links.db")
    first = SqliteStore(path)
    first.create_if_absent("aaaaaa", "https://a.example")
    first.close()
    assert SqliteStore(path).get("aaaaaa") == "https://a.example"


def test_concurrent_create_same_code_has_one_winner(tmp_path):
    store = SqliteStore(str(tmp_path / "links.db"))
    results: list[bool] = []

    def create(i):
        results.append(store.create_if_absent("aaaaaa", f"https://e.example/{i}"))

    threads = [threading.Thread(target=create, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 1
    assert len(results) == 20


def test_methods_after_close_raise_store_error(tmp_path):
    store = SqliteStore(str(tmp_path / "links.db"))
    store.close()
    with pytest.raises(StoreError):
        store.create_if_absent("aaaaaa", "https://a.example")
    with pytest.raises(StoreError):
        store.get("aaaaaa")
    with pytest.raises(StoreError):
        store.trim(keep=1, trigger=2)
