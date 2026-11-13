from urllib.parse import urlsplit

MAX_URL_LENGTH = 2000


def check_url(url: str, own_host: str) -> str | None:
    """Validate a URL a visitor wants shortened.

    Args:
        url: The submitted URL.
        own_host: Lowercase host of this service; links to it are refused.

    Returns:
        None if acceptable, else a short reason for the 400 response.
    """
    if not url or len(url) > MAX_URL_LENGTH:
        return f"url must be 1 to {MAX_URL_LENGTH} characters"
    # ASCII only also rejects IDN hosts; also no spaces or control characters.
    if not url.isascii() or any(c <= " " or c == "\x7f" for c in url):
        return "url must be ASCII without spaces or control characters"
    try:
        parts = urlsplit(url)
        host = parts.hostname
        parts.port  # noqa: B018 - raises ValueError on a bad port
    except ValueError:
        return "url is malformed"
    if parts.scheme not in ("http", "https"):
        return "scheme must be http or https"
    if not host:
        return "url needs a host"
    if parts.username is not None or parts.password is not None:
        return "url must not contain credentials"
    if host.rstrip(".") == own_host.lower():
        return "url points at this service"
    return None
