import pytest

from shortener.memory import MemoryStore
from shortener.sqlite_store import SqliteStore
from shortener.store import Store

STORES = ["memory", "sqlite"]


@pytest.fixture(params=STORES)
def store(request, tmp_path) -> Store:
    return {
        "memory": MemoryStore,
        "sqlite": lambda: SqliteStore(str(tmp_path / "links.db")),
    }[request.param]()


def test_first_create_returns_true(store):
    assert store.create_if_absent("aaaaaa", "https://a.example") is True


def test_second_create_keeps_first_url(store):
    store.create_if_absent("aaaaaa", "https://a.example")
    assert store.create_if_absent("aaaaaa", "https://b.example") is False
    assert store.get("aaaaaa") == "https://a.example"


def test_get_unknown_is_none(store):
    assert store.get("zzzzzz") is None


def fill(store, n):
    for i in range(n):
        store.create_if_absent(f"code{i:02}", f"https://e.example/{i}")


def test_trim_below_trigger_deletes_nothing(store):
    fill(store, 4)
    assert store.trim(keep=3, trigger=5) == 0
    assert all(store.get(f"code{i:02}") for i in range(4))


def test_trim_at_trigger_keeps_newest(store):
    fill(store, 5)
    assert store.trim(keep=3, trigger=5) == 2
    assert store.get("code00") is None
    assert store.get("code01") is None
    assert all(store.get(f"code{i:02}") for i in (2, 3, 4))
