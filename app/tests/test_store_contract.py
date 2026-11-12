import pytest

from shortener.memory import MemoryStore
from shortener.store import Store

STORES = ["memory"]


@pytest.fixture(params=STORES)
def store(request) -> Store:
    # Task 3 adds "sqlite" to STORES and a branch here.
    return {"memory": MemoryStore}[request.param]()


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
    assert store.get("code00") is not None


def test_trim_at_trigger_keeps_newest(store):
    fill(store, 5)
    assert store.trim(keep=3, trigger=5) == 2
    assert store.get("code00") is None
    assert store.get("code01") is None
    assert all(store.get(f"code{i:02}") for i in (2, 3, 4))
