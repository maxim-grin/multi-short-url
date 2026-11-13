import pytest

from shortener.urls import MAX_URL_LENGTH, check_url

OWN = "short.example"
LONG = "https://example.com/" + "a" * (MAX_URL_LENGTH - 20)


@pytest.mark.parametrize(
    "url", ["https://example.com", "HTTP://Example.com/a?b=c#d", LONG]
)
def test_accepts(url):
    assert len(LONG) == MAX_URL_LENGTH
    assert check_url(url, OWN) is None


@pytest.mark.parametrize(
    "url",
    [
        LONG + "a",
        "javascript:alert(1)",
        "data:text/html,x",
        "ftp://example.com",
        "file:///etc/passwd",
        "https://",
        "example.com",
        "https://exa mple.com",
        "https://example.com\n",
        "https://user:pw@example.com",
        "https://SHORT.example/x",
        "https://short.example./x",
        "https://example.com:99999/x",
        "https://example.com:http/x",
        "https://exämple.com/",
        "",
    ],
)
def test_rejects(url):
    reason = check_url(url, OWN)
    assert isinstance(reason, str)
    assert reason
