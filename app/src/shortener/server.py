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


def read_body(
    rfile: BufferedIOBase, content_length: str | None, limit: int = MAX_BODY
) -> bytes | None:
    if content_length is None or not content_length.isascii():
        return None
    if not content_length.isdigit() or int(content_length) > limit:
        return None
    return rfile.read(int(content_length))


def make_handler(app: Shortener) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _serve(self) -> None:
            try:
                response = self._respond()
            except Exception:  # noqa: BLE001 - last resort: never leak a traceback
                traceback.print_exc()
                response = text(500, "internal server error")
            self.send_response(response.status)
            for name, value in response.headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(response.body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(response.body)

        def _respond(self) -> Response:
            body = b""
            if self.command == "POST":
                length = self.headers.get("Content-Length")
                read = read_body(self.rfile, length)
                if read is None:
                    too_big = (length or "").isdigit() and int(length or 0) > MAX_BODY
                    self.close_connection = True  # the unread body would poison it
                    return error(
                        413 if too_big else 400,
                        "body too large" if too_big else "bad Content-Length",
                    )
                body = read
            return app.handle(
                to_request(self.command, self.path, dict(self.headers), body)
            )

        do_GET = do_HEAD = do_POST = _serve

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
        server.server_close()
        store.close()
