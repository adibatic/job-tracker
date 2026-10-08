"""Download one posting's text, rendering it in a browser only when needed.

Posting pages are fetched with plain HTTP first. If the text is too short or
never mentions requirements or qualifications (a sign the page builds its
content with JavaScript), Playwright is used instead, when it is installed.
Without Playwright, a short page's plain text is kept rather than lost; only
a page with almost no text fails.
"""

from . import http
from .detail import html_to_text

MIN_TEXT_LENGTH = 500
MIN_USABLE_LENGTH = 100
CONTENT_WORDS = ("requirement", "qualification", "responsibilit", "experience", "you will")


def _looks_complete(text: str) -> bool:
    lower = text.lower()
    return len(text) >= MIN_TEXT_LENGTH and any(w in lower for w in CONTENT_WORDS)


def _browser_page(url: str):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            f"{url} needs a browser to render. Install it with: "
            "pip install playwright && playwright install chromium"
        ) from exc
    return sync_playwright


def render_html(url: str) -> str:
    """The page's HTML after its JavaScript has run."""
    with _browser_page(url)() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=http.USER_AGENT)
        page.goto(url, wait_until="networkidle")
        html = page.content()
        browser.close()
    return html


def playwright_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


def fetch_posting_text(url: str, render: bool = False) -> str:
    if render:
        return html_to_text(render_html(url))
    text = html_to_text(http.get(url))
    if _looks_complete(text):
        return text
    if playwright_available():
        return html_to_text(render_html(url))
    if len(text) >= MIN_USABLE_LENGTH:
        return text            # short but real; better than nothing
    return html_to_text(render_html(url))   # raises with install instructions
