import json
import random

from shortener.core import (
    MAX_ATTEMPTS,
    MAX_BODY,
    Request,
    Response,
    Settings,
    Shortener,
)
from shortener.limiter import RateLimiter
from shortener.memory import MemoryStore
from shortener.store import KEEP, TRIGGER, StoreError

URL = "https://example.com/page"


class Clock:
    now = 0.0

    def __call__(self) -> float:
        return self.now


class Stub(MemoryStore):
    def __init__(self, fail_creates: int = 0, always: bool = False) -> None:
        super().__init__()
        self.fail_creates = fail_creates
        self.always = always
        self.creates = 0
        self.trims: list[tuple[int, int]] = []
        self.trim_error = False
        self.create_error = False

    def create_if_absent(self, code: str, url: str) -> bool:
        self.creates += 1
        if self.create_error:
            raise StoreError("down")
        if self.always or self.creates <= self.fail_creates:
            return False
        return super().create_if_absent(code, url)

    def trim(self, keep: int, trigger: int) -> int:
        self.trims.append((keep, trigger))
        if self.trim_error:
            raise StoreError("down")
        return 0


def make(store: MemoryStore | None = None, clock: Clock | None = None) -> Shortener:
    return Shortener(
        store or MemoryStore(),
        Settings("homelab", "https://x"),
        random.Random(1),
        RateLimiter(clock or Clock()),
    )


def post(s: Shortener, body: object) -> Response:
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    return s.handle(Request("POST", "/api/shorten", body=raw))


def test_create_returns_201_and_link_is_readable() -> None:
    s = make()
    r = post(s, {"url": URL})
    assert r.status == 201
    assert r.headers["Content-Type"] == "application/json"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    short = json.loads(r.body)["short_url"]
    assert short.startswith("https://x/homelab/")
    follow = s.handle(Request("GET", short.removeprefix("https://x")))
    assert (follow.status, follow.headers["Location"]) == (302, URL)


def test_same_url_twice_gives_two_codes() -> None:
    clock = Clock()
    s = make(clock=clock)
    first = json.loads(post(s, {"url": URL}).body)["short_url"]
    clock.now = 1.0
    assert json.loads(post(s, {"url": URL}).body)["short_url"] != first


def test_invalid_url_is_400_with_reason() -> None:
    r = post(make(), {"url": "ftp://example.com"})
    assert r.status == 400
    assert json.loads(r.body) == {"error": "scheme must be http or https"}


def test_own_host_is_rejected() -> None:
    assert post(make(), {"url": "https://X/abc"}).status == 400


def test_bad_bodies_are_400() -> None:
    s = make()
    for body in (b"nope", b"\xff", [URL], {}, {"url": 5}, {"url": None}):
        r = post(s, body)
        assert r.status == 400, body
        assert "error" in json.loads(r.body)


def test_oversized_body_is_413() -> None:
    r = post(make(), b" " * (MAX_BODY + 1))
    assert r.status == 413
    assert "error" in json.loads(r.body)


def test_invalid_request_keeps_the_token() -> None:
    s = make()
    assert post(s, {"url": "nope"}).status == 400
    assert post(s, b"{").status == 400
    assert post(s, {"url": URL}).status == 201


def test_rate_limit_429_then_recovers() -> None:
    clock = Clock()
    s = make(clock=clock)
    assert post(s, {"url": URL}).status == 201
    r = post(s, {"url": URL})
    assert r.status == 429
    assert r.headers["Retry-After"] == "1"
    assert "error" in json.loads(r.body)
    clock.now = 1.0
    assert post(s, {"url": URL}).status == 201


def test_collisions_retry_with_new_code() -> None:
    store = Stub(fail_creates=2)
    assert post(make(store), {"url": URL}).status == 201
    assert store.creates == 3


def test_persistent_collisions_give_503_after_max_attempts() -> None:
    store = Stub(always=True)
    assert post(make(store), {"url": URL}).status == 503
    assert store.creates == MAX_ATTEMPTS


def test_store_error_on_create_is_503() -> None:
    store = Stub()
    store.create_error = True
    r = post(make(store), {"url": URL})
    assert r.status == 503
    assert "error" in json.loads(r.body)


def test_trim_runs_once_after_create() -> None:
    store = Stub()
    post(make(store), {"url": URL})
    assert store.trims == [(KEEP, TRIGGER)]


def test_trim_failure_still_201() -> None:
    store = Stub()
    store.trim_error = True
    assert post(make(store), {"url": URL}).status == 201


def test_other_methods_on_shorten_are_405() -> None:
    r = make().handle(Request("GET", "/api/shorten"))
    assert (r.status, r.headers["Allow"]) == (405, "POST")
