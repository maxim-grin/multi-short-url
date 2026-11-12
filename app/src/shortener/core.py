import random
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from .codes import is_code
from .limiter import RateLimiter
from .store import Store, StoreError

NOSNIFF = {"X-Content-Type-Options": "nosniff"}
TEXT = {"Content-Type": "text/plain; charset=utf-8", **NOSNIFF}


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
        if path == "/healthz":
            if method in ("GET", "HEAD"):
                return text(200, "ok")
            return text(405, "method not allowed", Allow="GET, HEAD")
        if path == "/api/shorten":
            return text(405, "method not allowed", Allow="POST")
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
