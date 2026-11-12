from urllib.parse import urlsplit

MAX_URL_LENGTH = 2000


def check_url(url: str, own_host: str) -> str | None:
    """Return None if url is acceptable, else a short reason."""
    if not url or len(url) > MAX_URL_LENGTH:
        return f"url must be 1 to {MAX_URL_LENGTH} characters"
    # ASCII only also rejects IDN hosts; also no spaces or control characters.
    if not url.isascii() or any(c <= " " or c == "\x7f" for c in url):
        return "url must be ASCII without spaces or control characters"
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return "url is malformed"
    if parts.scheme not in ("http", "https"):
        return "scheme must be http or https"
    if not host:
        return "url needs a host"
    if parts.username is not None or parts.password is not None:
        return "url must not contain credentials"
    if host == own_host.lower():
        return "url points at this service"
    return None
