"""Polite HTTP: identify ourselves, respect robots.txt, pause between requests."""

import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

USER_AGENT = "job-tracker/0.1 (personal job research; low volume)"
DELAY_SECONDS = 3.0

_robots: dict[str, urllib.robotparser.RobotFileParser] = {}
_last_request = 0.0


def allowed(url: str) -> bool:
    """True if robots.txt of the URL's host allows our user agent to fetch it."""
    parts = urlparse(url)
    host = f"{parts.scheme}://{parts.netloc}"
    if host not in _robots:
        rp = urllib.robotparser.RobotFileParser(host + "/robots.txt")
        try:
            rp.read()
        except OSError:
            # No readable robots.txt: treat as allowed, as crawlers usually do.
            rp.parse([])
        _robots[host] = rp
    return _robots[host].can_fetch(USER_AGENT, url)


def get(url: str, timeout: float = 30.0) -> str:
    """Fetch a URL as text, waiting DELAY_SECONDS since the previous request."""
    global _last_request
    if not allowed(url):
        raise PermissionError(f"robots.txt disallows {url}")
    wait = DELAY_SECONDS - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    _last_request = time.monotonic()
    response.raise_for_status()
    if "charset" not in response.headers.get("Content-Type", "").lower():
        # requests falls back to ISO-8859-1, which garbles dashes and accents.
        response.encoding = "utf-8"
    return response.text
