import io

import pytest

from shortener.server import ConfigError, load_config, read_body, to_request

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
