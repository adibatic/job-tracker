"""Read a careers page into Listings.

Two page readers, for sites without a job-board feed:

  parse_listings  a table whose header has a title column (for example TITLE,
                  LOCATION, COUNTRY, CLOSING DATE). Columns are found by
                  header text, so order and wording can vary.
  parse_links     any page: every link whose address looks like a job posting
                  (or matches the site's pattern= option) becomes a Listing.
"""

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

LIST_URL = "https://spaceco.example/career/job-opportunities/"

HEADER_NAMES = {
    "title": ("title", "position", "job title", "job", "role", "vacancy"),
    "location": ("location", "city", "office", "place"),
    "country": ("country",),
    "closing_date": ("closing date", "deadline", "apply by", "last application date",
                     "application deadline"),
}

# Address segments that name a list of jobs. A posting's address continues
# after one of them (/careers/flight-engineer); the list itself (/careers) does not.
LIST_SEGMENTS = {"job", "jobs", "career", "careers", "position", "positions", "vacancy",
                 "vacancies", "opening", "openings", "opportunity", "opportunities",
                 "job-opportunities", "role", "roles", "stellen", "lediga-jobb", "o",
                 "join-us", "work-with-us"}
# Segments that are a single posting by themselves: /job-1234, /position_abc.
POSTING_PREFIXES = ("job-", "job_", "position-", "vacancy-", "opening-", "role-")


@dataclass
class Listing:
    title: str
    location: str
    country: str
    closing_date: str
    url: str
    text: str = ""          # full posting text, when the source already provides it


def _clean(text: str) -> str:
    return " ".join(text.split())


def _column(headers: list[str], field: str) -> int | None:
    for i, header in enumerate(headers):
        if header in HEADER_NAMES[field]:
            return i
    return None


def parse_listings(html: str, base_url: str = LIST_URL) -> list[Listing]:
    """One Listing per row, in every table whose header has a title column."""
    soup = BeautifulSoup(html, "html.parser")
    listings: list[Listing] = []
    for table in soup.find_all("table"):
        header_row = table.find("tr")
        if header_row is None:
            continue
        headers = [_clean(c.get_text()).lower().rstrip(":")
                   for c in header_row.find_all(["th", "td"])]
        col = {f: _column(headers, f) for f in HEADER_NAMES}
        if col["title"] is None:
            continue
        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            link = row.find("a", href=True)
            if link is None or len(cells) < len(headers):
                continue

            def cell(field: str) -> str:
                i = col[field]
                return _clean(cells[i].get_text()) if i is not None else ""

            listings.append(Listing(cell("title"), cell("location"), cell("country"),
                                    cell("closing_date"), urljoin(base_url, link["href"])))
    return listings


def _looks_like_job(url: str, page_url: str) -> bool:
    path = urlparse(url).path.lower().strip("/")
    page_path = urlparse(page_url).path.lower().strip("/")
    if not path or page_path.startswith(path):      # the page itself, or a parent of it
        return False
    segments = path.split("/")
    for i, segment in enumerate(segments):
        if segment in LIST_SEGMENTS and i < len(segments) - 1:
            return True
        if segment.startswith(POSTING_PREFIXES):
            return True
    return False


def parse_links(html: str, base_url: str, pattern: str = "") -> list[Listing]:
    """Links that point at job postings, one Listing each, first occurrence kept."""
    soup = BeautifulSoup(html, "html.parser")
    regex = re.compile(pattern) if pattern else None
    seen: set[str] = set()
    listings: list[Listing] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        url = urljoin(base_url, href).split("#")[0]
        title = _clean(a.get_text())
        if url in seen or not (3 <= len(title) <= 150):
            continue
        matches = regex.search(url) if regex else _looks_like_job(url, base_url)
        if not matches:
            continue
        seen.add(url)
        listings.append(Listing(title, "", "", "", url))
    return listings
