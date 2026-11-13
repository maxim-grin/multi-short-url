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
    main,
    make_handler,
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


def test_keep_is_read_from_the_environment() -> None:
    assert load_config(ENV).settings.keep == 10_000
    assert load_config({**ENV, "SHORTENER_KEEP": "500"}).settings.keep == 500
    for bad in ("many", "0"):
        with pytest.raises(ConfigError, match=r"(?i)keep"):
            load_config({**ENV, "SHORTENER_KEEP": bad})


def test_bad_prefix_is_a_config_error() -> None:
    with pytest.raises(ConfigError, match="prefix"):
        load_config({**ENV, "SHORTENER_PREFIX": "Bad!"})


def test_to_request_drops_query_and_fragment() -> None:
    request = to_request("GET", "/homelab/abc123?utm=1#x", {"Host": "h"}, b"")
    assert request.path == "/homelab/abc123"
    assert request.method == "GET"


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
    assert _post(None, b"").status == 400  # empty body is not valid JSON
    assert _post("2", b"{}").status == 400  # JSON without a url


def test_post_without_length_is_routed_by_the_core() -> None:
    no_body = io.BytesIO()
    assert respond(_app(), "POST", "/healthz", {}, no_body).status == 405
    assert respond(_app(), "POST", "/nope", {}, no_body).status == 404


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


def test_unopenable_database_exits_with_one_line(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in {
        **ENV,
        "SHORTENER_DB_PATH": str(tmp_path / "no" / "x.db"),
    }.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(SystemExit) as e:
        main()
    assert str(e.value).startswith("shortener: ")
