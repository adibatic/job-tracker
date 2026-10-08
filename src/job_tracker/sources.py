"""Get the list of postings for one site, whatever kind of site it is.

Job-board feeds (greenhouse, lever, ashby, recruitee, personio) return every
posting with its full text in one request, so no posting page is downloaded
afterwards. Their addresses and fields follow each provider's public job-board
documentation as I know it; if a feed changes, only its function here needs
updating, and its test in tests/test_sources.py shows the expected shape.

table and links sources read the careers page itself (see listing.py); each
posting's text is then downloaded from its own page.
"""

import html
import json
import xml.etree.ElementTree as ET

from . import http
from .detail import html_to_text
from .listing import Listing, parse_links, parse_listings
from .sites import Site


def _text(fragment: str | None) -> str:
    return html_to_text(fragment or "") if fragment else ""


def greenhouse(site: Site) -> list[Listing]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{site.board}/jobs?content=true"
    data = json.loads(http.get(url))
    return [
        Listing(
            title=job.get("title", ""),
            location=(job.get("location") or {}).get("name", ""),
            country="",
            closing_date="",
            url=job.get("absolute_url", ""),
            text=_text(html.unescape(job.get("content") or "")),   # content is escaped HTML
        )
        for job in data.get("jobs", [])
    ]


def lever(site: Site) -> list[Listing]:
    data = json.loads(http.get(f"https://api.lever.co/v0/postings/{site.board}?mode=json"))
    listings = []
    for job in data:
        parts = [job.get("descriptionPlain", "")]
        for block in job.get("lists", []):
            parts += [block.get("text", ""), _text(block.get("content", ""))]
        parts.append(job.get("additionalPlain", ""))
        categories = job.get("categories") or {}
        listings.append(Listing(
            title=job.get("text", ""),
            location=categories.get("location", ""),
            country="",
            closing_date="",
            url=job.get("hostedUrl", ""),
            text="\n".join(p for p in parts if p),
        ))
    return listings


def ashby(site: Site) -> list[Listing]:
    data = json.loads(http.get(f"https://api.ashbyhq.com/posting-api/job-board/{site.board}"))
    return [
        Listing(
            title=job.get("title", ""),
            location=job.get("location", "") or "",
            country="",
            closing_date="",
            url=job.get("jobUrl", "") or job.get("applyUrl", ""),
            text=job.get("descriptionPlain") or _text(job.get("descriptionHtml")),
        )
        for job in data.get("jobs", [])
        if job.get("isListed", True)
    ]


def recruitee(site: Site) -> list[Listing]:
    data = json.loads(http.get(f"https://{site.board}.recruitee.com/api/offers/"))
    return [
        Listing(
            title=offer.get("title", ""),
            location=offer.get("location", "") or "",
            country=offer.get("country", "") or "",
            closing_date="",
            url=offer.get("careers_url", ""),
            text="\n".join(t for t in (_text(offer.get("description")),
                                       "Requirements",
                                       _text(offer.get("requirements"))) if t),
        )
        for offer in data.get("offers", [])
    ]


def personio(site: Site) -> list[Listing]:
    base = site.url.split("/xml")[0].rstrip("/")
    if not base.startswith("http") or "personio" not in base:
        base = f"https://{site.board}.jobs.personio.de"
    root = ET.fromstring(http.get(f"{base}/xml"))
    listings = []
    for position in root.iter("position"):
        def field(tag: str) -> str:
            node = position.find(tag)
            return (node.text or "").strip() if node is not None else ""

        parts = []
        for desc in position.iter("jobDescription"):
            name, value = desc.find("name"), desc.find("value")
            parts.append((name.text or "") if name is not None else "")
            parts.append(_text(value.text if value is not None else ""))
        listings.append(Listing(
            title=field("name"),
            location=field("office"),
            country="",
            closing_date="",
            url=f"{base}/job/{field('id')}",
            text="\n".join(p for p in parts if p),
        ))
    return listings


def page_html(site: Site) -> str:
    if not site.render:
        return http.get(site.url)
    from .fetch import render_html
    return render_html(site.url)


def table(site: Site) -> list[Listing]:
    return parse_listings(page_html(site), base_url=site.url)


def links(site: Site) -> list[Listing]:
    return parse_links(page_html(site), base_url=site.url, pattern=site.pattern)


READERS = {
    "table": table,
    "links": links,
    "greenhouse": greenhouse,
    "lever": lever,
    "ashby": ashby,
    "recruitee": recruitee,
    "personio": personio,
}


def fetch_listings(site: Site) -> tuple[list[Listing], str]:
    """Listings for a site, and the source that produced them.

    A table site that turns out to have no job table is read again as links,
    so an unknown careers page still gives a result.
    """
    listings = READERS[site.source](site)
    if site.source == "table" and not listings:
        listings = parse_links(page_html(site), base_url=site.url, pattern=site.pattern)
        return listings, "links"
    return listings, site.source
