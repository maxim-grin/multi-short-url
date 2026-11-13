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
    """The environment is missing or has an invalid setting."""


@dataclass(frozen=True)
class Config:
    """Everything the process reads from its environment.

    Attributes:
        settings: Prefix and base URL for the core.
        db_path: SQLite file location.
        port: TCP port to listen on.
    """

    settings: Settings
    db_path: str
    port: int


def load_config(env: Mapping[str, str]) -> Config:
    """Read the configuration.

    Args:
        env: Environment variables; SHORTENER_PREFIX, SHORTENER_BASE_URL and
            SHORTENER_DB_PATH are required, PORT defaults to 8080.

    Raises:
        ConfigError: A variable is missing or invalid.
    """
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
    """Translate HTTP server values into a core Request.

    Args:
        method: HTTP method.
        target: Request target; the query string and fragment are dropped.
        headers: Request headers.
        body: Raw body.
    """
    path = target.split("?", 1)[0].split("#", 1)[0]
    return Request(method, path, headers, body)


def _length(content_length: str | None, limit: int) -> int | Response:
    """Parse Content-Length.

    Args:
        content_length: Header value, or None if absent.
        limit: Largest body accepted.

    Returns:
        The byte count to read, or a 400 or 413 Response.
    """
    # The one place that parses Content-Length and picks 413 versus 400.
    if content_length is None:  # no header means an empty body, as on other wrappers
        return 0
    if not (content_length.isascii() and content_length.isdigit()):
        return error(400, "bad Content-Length")
    if len(content_length) > 10 or int(content_length) > limit:  # cap before int()
        return error(413, "body too large")
    return int(content_length)


def respond(
    app: Shortener,
    method: str,
    target: str,
    headers: Mapping[str, str],
    rfile: BufferedIOBase,
) -> Response:
    """Run one request through the core; any crash becomes a 500.

    Args:
        app: The core.
        method: HTTP method.
        target: Request target.
        headers: Request headers.
        rfile: Stream the body is read from, for POST only.
    """
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
    """Return the body to send: empty for HEAD, else the response body.

    Args:
        method: HTTP method of the request.
        response: The core's response.
    """
    return b"" if method == "HEAD" else response.body


def make_handler(app: Shortener) -> type[BaseHTTPRequestHandler]:
    """Build a request handler class bound to app.

    Args:
        app: The core every request goes to.
    """

    class Handler(BaseHTTPRequestHandler):
        # shortcut: timeout is per read, not per request; put a buffering front end
        # or a thread cap in front when exposed beyond the LAN
        timeout = 10

        def _serve(self) -> None:
            """Answer the current request; every method shares this."""
            response = respond(app, self.command, self.path, self.headers, self.rfile)  # type: ignore[arg-type]
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
    """Read the environment, then serve until SIGTERM or SIGINT."""
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
