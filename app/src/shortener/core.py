import base64
import hashlib
import json
import random
import re
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from importlib.resources import files
from urllib.parse import urlsplit

from .codes import is_code, new_code
from .limiter import RateLimiter
from .store import KEEP, TRIGGER, Store, StoreError
from .urls import check_url

NOSNIFF = {"X-Content-Type-Options": "nosniff"}
JSON = {"Content-Type": "application/json", **NOSNIFF}
MAX_ATTEMPTS = 5
MAX_BODY = 8192
TEXT = {"Content-Type": "text/plain; charset=utf-8", **NOSNIFF}


def _hash(page: str, tag: str) -> str:
    block = re.search(f"<{tag}>(.*?)</{tag}>", page, re.DOTALL)
    assert block, tag
    digest = hashlib.sha256(block[1].encode()).digest()
    return f"'sha256-{base64.b64encode(digest).decode()}'"


_PAGE = files("shortener").joinpath("page.html").read_text(encoding="utf-8")
_PAGE_BYTES = _PAGE.encode()
HTML = {
    "Content-Type": "text/html; charset=utf-8",
    "Content-Security-Policy": (
        f"default-src 'none'; script-src {_hash(_PAGE, 'script')}; "
        f"style-src {_hash(_PAGE, 'style')}; connect-src 'self'"
    ),
    **NOSNIFF,
}


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class Settings:
    prefix: str
    base_url: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9]*", self.prefix):
            raise ValueError(
                "prefix must be lowercase letters and digits, starting with a letter"
            )
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        object.__setattr__(self, "base_url", self.base_url.removesuffix("/"))


def error(status: int, reason: str, **extra: str) -> Response:
    return Response(status, {**JSON, **extra}, json.dumps({"error": reason}).encode())


def text(status: int, body: str, **extra: str) -> Response:
    return Response(status, {**TEXT, **extra}, body.encode())


class Shortener:
    def __init__(
        self, store: Store, settings: Settings, rng: random.Random, limiter: RateLimiter
    ) -> None:
        self.store = store
        self.settings = settings
        self.rng = rng
        self.limiter = limiter

    def handle(self, request: Request) -> Response:
        method, path = request.method, request.path
        if path == "/":
            if method in ("GET", "HEAD"):
                return Response(200, dict(HTML), _PAGE_BYTES)
            return text(405, "method not allowed", Allow="GET, HEAD")
        if path == "/healthz":
            if method in ("GET", "HEAD"):
                return text(200, "ok")
            return text(405, "method not allowed", Allow="GET, HEAD")
        if path == "/api/shorten":
            if method != "POST":
                return text(405, "method not allowed", Allow="POST")
            return self._create(request.body)
        parts = path.split("/")
        if (
            len(parts) == 3
            and parts[:2] == ["", self.settings.prefix]
            and is_code(parts[2])
        ):
            if method not in ("GET", "HEAD"):
                return text(405, "method not allowed", Allow="GET, HEAD")
            return self._redirect(parts[2])
        return text(404, "not found")

    def _redirect(self, code: str) -> Response:
        try:
            url = self.store.get(code)
        except StoreError:
            return text(503, "service unavailable")
        if url is None:
            return text(404, "not found")
        return Response(302, {"Location": url, **NOSNIFF}, b"")

    def _create(self, body: bytes) -> Response:
        if len(body) > MAX_BODY:
            return error(413, "body too large")
        try:
            data = json.loads(body)
        except ValueError:  # includes bad UTF-8
            return error(400, "body must be JSON")
        url = data.get("url") if isinstance(data, dict) else None
        if not isinstance(url, str):
            return error(400, 'body must be {"url": "<string>"}')
        own_host = (urlsplit(self.settings.base_url).hostname or "").lower()
        if reason := check_url(url, own_host):
            return error(400, reason)
        if not self.limiter.allow():
            return error(
                429,
                "rate limit exceeded",
                **{"Retry-After": str(self.limiter.retry_after())},
            )
        try:
            for _ in range(MAX_ATTEMPTS):
                code = new_code(self.rng)
                if self.store.create_if_absent(code, url):
                    break
            else:
                return error(503, "service unavailable")
        except StoreError:
            return error(503, "service unavailable")
        with suppress(StoreError):  # the link exists; the next create retries the trim
            self.store.trim(KEEP, TRIGGER)
        short = f"{self.settings.base_url}/{self.settings.prefix}/{code}"
        return Response(201, dict(JSON), json.dumps({"short_url": short}).encode())
