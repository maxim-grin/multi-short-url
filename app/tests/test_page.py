import base64
import hashlib
import random
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path

from shortener.core import Request, Settings, Shortener
from shortener.limiter import RateLimiter
from shortener.memory import MemoryStore


def get(method: str = "GET"):
    app = Shortener(
        MemoryStore(),
        Settings("homelab", "https://x"),
        random.Random(1),
        RateLimiter(lambda: 0.0),
    )
    return app.handle(Request(method, "/"))


def sha(block: str) -> str:
    return (
        "sha256-" + base64.b64encode(hashlib.sha256(block.encode()).digest()).decode()
    )


def test_page_served_with_content_type() -> None:
    r = get()
    assert r.status == 200
    assert r.headers["Content-Type"] == "text/html; charset=utf-8"
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_page_has_ids_and_api_path() -> None:
    html = get().body.decode()
    for name in ("long-url", "shorten", "short-url", "copy", "error"):
        assert f'id="{name}"' in html
    assert "/api/shorten" in html


def test_csp_allows_only_the_inline_script_and_style_by_hash() -> None:
    r = get()
    html = r.body.decode()
    csp = r.headers["Content-Security-Policy"]
    scripts = re.findall(r"<script>(.*?)</script>", html, re.DOTALL)
    styles = re.findall(r"<style>(.*?)</style>", html, re.DOTALL)
    assert len(scripts) == 1
    assert len(styles) == 1
    assert f"script-src '{sha(scripts[0])}'" in csp
    assert f"style-src '{sha(styles[0])}'" in csp
    assert "default-src 'none'" in csp
    assert "connect-src 'self'" in csp
    assert "unsafe-inline" not in csp
    assert " style=" not in html


def test_page_references_no_external_host() -> None:
    html = get().body.decode()
    assert not re.search(r"(src|href)\s*=\s*[\"']?(https?:)?//", html)


def test_head_ok_and_post_rejected() -> None:
    assert get("HEAD").status == 200
    assert get("POST").status == 405


def test_page_is_in_the_built_wheel() -> None:
    app_dir = Path(__file__).parent.parent
    with tempfile.TemporaryDirectory() as out:
        subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", out],
            cwd=app_dir,
            check=True,
            capture_output=True,
        )
        wheel = next(Path(out).glob("*.whl"))
        assert "shortener/page.html" in zipfile.ZipFile(wheel).namelist()
