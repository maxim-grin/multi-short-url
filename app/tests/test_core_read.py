import random
from typing import NoReturn

import pytest

from shortener.core import Request, Settings, Shortener
from shortener.limiter import RateLimiter
from shortener.memory import MemoryStore
from shortener.store import StoreError

URL = "https://example.com/a%20b?x=1&y=%7E#frag"


class BrokenStore(MemoryStore):
    def get(self, code: str) -> NoReturn:
        raise StoreError("down")


def make(store: MemoryStore | None = None) -> Shortener:
    return Shortener(
        store or MemoryStore(),
        Settings("homelab", "https://x"),
        random.Random(1),
        RateLimiter(lambda: 0.0),
    )


def seeded() -> Shortener:
    store = MemoryStore()
    store.create_if_absent("k3fq9x", URL)
    return make(store)


def test_redirect_get_and_head() -> None:
    for method in ("GET", "HEAD"):
        r = seeded().handle(Request(method, "/homelab/k3fq9x"))
        assert r.status == 302
        assert r.headers["Location"] == URL
        assert r.body == b""


def test_unknown_code_is_plain_404() -> None:
    r = seeded().handle(Request("GET", "/homelab/zzzzzz"))
    assert r.status == 404
    assert r.headers["Content-Type"].startswith("text/plain")


def test_other_prefix_is_404() -> None:
    assert seeded().handle(Request("GET", "/other/k3fq9x")).status == 404


def test_malformed_code_skips_store() -> None:
    s = make(BrokenStore())
    for path in ("/homelab/ABC", "/homelab/k3fq9x/", "/homelab/"):
        assert s.handle(Request("GET", path)).status == 404


def test_healthz_ignores_store() -> None:
    r = make(BrokenStore()).handle(Request("GET", "/healthz"))
    assert (r.status, r.body) == (200, b"ok")


def test_unknown_path_404() -> None:
    assert make().handle(Request("GET", "/nope")).status == 404


def test_wrong_method_405_with_allow() -> None:
    r = seeded().handle(Request("POST", "/homelab/k3fq9x"))
    assert r.status == 405
    assert "GET" in r.headers["Allow"]
    assert make().handle(Request("GET", "/api/shorten")).status == 405
    assert make().handle(Request("POST", "/healthz")).status == 405


def test_store_error_is_503_plain() -> None:
    r = make(BrokenStore()).handle(Request("GET", "/homelab/k3fq9x"))
    assert r.status == 503
    assert r.headers["Content-Type"].startswith("text/plain")


def test_settings_validation() -> None:
    for prefix, base in (
        ("Home", "https://x"),
        ("home", "ftp://x"),
        ("1h", "https://x"),
    ):
        with pytest.raises(ValueError, match="must"):
            Settings(prefix, base)
    for base in (
        "https://",
        "https://x/sub",
        "https:///sub",
        "https://x?q=1",
        "https://x#f",
    ):
        with pytest.raises(ValueError, match="base_url"):
            Settings("home", base)
    assert Settings("home", "https://x/").base_url == "https://x"


def test_every_response_has_nosniff() -> None:
    s = seeded()
    for req in (
        Request("GET", "/homelab/k3fq9x"),
        Request("GET", "/homelab/zzzzzz"),
        Request("GET", "/healthz"),
        Request("GET", "/nope"),
        Request("POST", "/healthz"),
    ):
        assert s.handle(req).headers["X-Content-Type-Options"] == "nosniff"


def test_settings_keep_defaults_to_10000_and_trigger_is_10_percent_above() -> None:
    s = Settings("home", "https://x")
    assert (s.keep, s.trigger) == (10_000, 11_000)
    assert Settings("home", "https://x", keep=1000).trigger == 1100


@pytest.mark.parametrize("keep", [0, -1])
def test_settings_keep_must_be_positive(keep: int) -> None:
    with pytest.raises(ValueError, match="keep"):
        Settings("home", "https://x", keep=keep)
