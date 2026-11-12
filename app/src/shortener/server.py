import os
import random
import signal
import sys
import threading
import time
import traceback
from collections.abc import Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BufferedIOBase

from .core import MAX_BODY, Request, Response, Settings, Shortener, error, text
from .limiter import RateLimiter
from .sqlite_store import SqliteStore


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    settings: Settings
    db_path: str
    port: int


def load_config(env: Mapping[str, str]) -> Config:
    missing = [
        n
        for n in ("SHORTENER_PREFIX", "SHORTENER_BASE_URL", "SHORTENER_DB_PATH")
        if not env.get(n)
    ]
    if missing:
        raise ConfigError(f"missing environment variable: {missing[0]}")
    try:
        port = int(env.get("PORT", "8080"))
    except ValueError:
        raise ConfigError("PORT must be a number") from None
    try:
        settings = Settings(env["SHORTENER_PREFIX"], env["SHORTENER_BASE_URL"])
    except ValueError as e:
        raise ConfigError(str(e)) from None
    return Config(settings, env["SHORTENER_DB_PATH"], port)


def to_request(
    method: str, target: str, headers: Mapping[str, str], body: bytes
) -> Request:
    path = target.split("?", 1)[0].split("#", 1)[0]
    return Request(method, path, headers, body)


def _length(content_length: str | None, limit: int) -> int | Response:
    # The one place that parses Content-Length and picks 413 versus 400.
    if content_length is None or not (
        content_length.isascii() and content_length.isdigit()
    ):
        return error(400, "bad Content-Length")
    if len(content_length) > 10 or int(content_length) > limit:  # cap before int()
        return error(413, "body too large")
    return int(content_length)


def read_body(
    rfile: BufferedIOBase, content_length: str | None, limit: int = MAX_BODY
) -> bytes | None:
    length = _length(content_length, limit)
    return None if isinstance(length, Response) else rfile.read(length)


def respond(
    app: Shortener,
    method: str,
    target: str,
    headers: Mapping[str, str],
    rfile: BufferedIOBase,
) -> Response:
    try:
        body = b""
        if method == "POST":
            length = _length(headers.get("Content-Length"), MAX_BODY)
            if isinstance(length, Response):
                return length
            body = rfile.read(length)
        return app.handle(to_request(method, target, headers, body))
    except Exception:  # noqa: BLE001 - last resort: never leak a traceback
        traceback.print_exc()
        return text(500, "internal server error")


def body_for(method: str, response: Response) -> bytes:
    return b"" if method == "HEAD" else response.body


def make_handler(app: Shortener) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        timeout = 10  # a stalled client must not hold a thread forever

        def _serve(self) -> None:
            response = respond(app, self.command, self.path, self.headers, self.rfile)  # type: ignore[arg-type]
            if response.status in (400, 413):
                self.close_connection = True  # an unread body would poison it
            self.send_response(response.status)
            for name, value in response.headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(response.body)))
            self.end_headers()
            self.wfile.write(body_for(self.command, response))

        do_GET = do_HEAD = do_POST = _serve
        do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _serve

    return Handler


def main() -> None:
    try:
        config = load_config(os.environ)
    except ConfigError as e:
        sys.exit(f"shortener: {e}")
    store = SqliteStore(config.db_path)
    app = Shortener(
        store, config.settings, random.SystemRandom(), RateLimiter(time.monotonic)
    )
    server = ThreadingHTTPServer(("0.0.0.0", config.port), make_handler(app))
    stop = lambda *_: threading.Thread(target=server.shutdown).start()  # noqa: E731
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever()
    finally:
        # Known limit: a request thread may be mid-request; the process is exiting.
        server.server_close()
        store.close()
