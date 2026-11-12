import io
import random

import pytest

from shortener.core import Request, Response, Settings, Shortener, text
from shortener.limiter import RateLimiter
from shortener.memory import MemoryStore
from shortener.server import (
    ConfigError,
    body_for,
    load_config,
    make_handler,
    read_body,
    respond,
    to_request,
)

ENV = {
    "SHORTENER_PREFIX": "homelab",
    "SHORTENER_BASE_URL": "http://localhost:8080",
    "SHORTENER_DB_PATH": "/tmp/x.db",
}


def test_load_config_defaults_port() -> None:
    config = load_config(ENV)
    assert config.port == 8080
    assert config.settings.prefix == "homelab"
    assert config.db_path == "/tmp/x.db"


@pytest.mark.parametrize("name", sorted(ENV))
def test_missing_required_variable_is_named(name: str) -> None:
    env = {k: v for k, v in ENV.items() if k != name}
    with pytest.raises(ConfigError, match=name):
        load_config(env)


def test_port_is_read_and_must_be_numeric() -> None:
    assert load_config({**ENV, "PORT": "9000"}).port == 9000
    with pytest.raises(ConfigError, match="PORT"):
        load_config({**ENV, "PORT": "http"})


def test_bad_prefix_is_a_config_error() -> None:
    with pytest.raises(ConfigError, match="prefix"):
        load_config({**ENV, "SHORTENER_PREFIX": "Bad!"})


def test_to_request_drops_query_and_fragment() -> None:
    request = to_request("GET", "/homelab/abc123?utm=1#x", {"Host": "h"}, b"")
    assert request.path == "/homelab/abc123"
    assert request.method == "GET"


@pytest.mark.parametrize("length", ["9999", "-1", "abc", None])
def test_read_body_rejects_without_reading(length: str | None) -> None:
    rfile = io.BytesIO(b"x" * 20)
    assert read_body(rfile, length) is None
    assert rfile.tell() == 0


def test_read_body_returns_the_bytes() -> None:
    assert read_body(io.BytesIO(b"hello world"), "5") == b"hello"


def test_huge_content_length_is_too_large_not_an_error() -> None:
    rfile = io.BytesIO(b"x")
    assert read_body(rfile, "9" * 5000) is None
    assert rfile.tell() == 0


def _app(cls: type[Shortener] = Shortener) -> Shortener:
    settings = Settings("homelab", "http://h")
    return cls(MemoryStore(), settings, random.Random(1), RateLimiter(lambda: 0.0))


class _Boom(Shortener):
    def handle(self, request: Request) -> Response:
        raise RuntimeError("secret detail")


def _post(length: str | None, body: bytes = b"") -> Response:
    headers = {} if length is None else {"Content-Length": length}
    return respond(_app(), "POST", "/api/shorten", headers, io.BytesIO(body))


def test_respond_maps_body_problems() -> None:
    assert _post("9000").status == 413
    assert _post("9" * 5000).status == 413
    assert _post("abc").status == 400
    assert _post(None).status == 400
    assert _post("2", b"{}").status == 400  # JSON without a url


def test_respond_turns_a_crash_into_a_constant_500(
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = respond(_app(_Boom), "GET", "/", {}, io.BytesIO())
    assert out.status == 500
    assert out.body == b"internal server error"
    assert b"secret" not in out.body
    assert "secret detail" in capsys.readouterr().err


@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH", "OPTIONS"])
def test_respond_gives_405_for_other_methods(method: str) -> None:
    out = respond(_app(), method, "/", {}, io.BytesIO())
    assert out.status == 405
    assert "Allow" in out.headers


def test_head_never_gets_a_body() -> None:
    response = text(404, "not found")
    assert body_for("HEAD", response) == b""
    assert body_for("GET", response) == b"not found"


def test_handler_has_a_socket_timeout() -> None:
    assert 0 < make_handler(_app()).timeout <= 30
