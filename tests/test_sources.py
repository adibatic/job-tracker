"""Each job-board reader against a sample of that provider's feed, offline."""

from pathlib import Path

import pytest

from job_tracker import http, sources
from job_tracker.detail import parse_posting
from job_tracker.sites import parse_line

FEEDS = Path(__file__).parent / "fixtures" / "feeds"


@pytest.fixture
def serve(monkeypatch):
    """Answer http.get(url) from a {url_fragment: fixture file} map."""
    def install(routes: dict[str, str]):
        def fake_get(url, timeout=30.0):
            for fragment, name in routes.items():
                if fragment in url:
                    return (FEEDS / name).read_text(encoding="utf-8")
            raise AssertionError(f"unexpected request: {url}")
        monkeypatch.setattr(http, "get", fake_get)
    return install


def test_greenhouse(serve):
    serve({"boards-api.greenhouse.io/v1/boards/acme/jobs": "greenhouse.json"})
    (job,), source = sources.fetch_listings(parse_line("https://boards.greenhouse.io/acme"))
    assert source == "greenhouse"
    assert (job.title, job.location) == ("GNC Engineer", "Stockholm")
    assert parse_posting(job.text).sections["requirements"] == ["Python and orbit simulation"]


def test_lever(serve):
    serve({"api.lever.co/v0/postings/acme": "lever.json"})
    (job,), _ = sources.fetch_listings(parse_line("https://jobs.lever.co/acme"))
    assert (job.title, job.location, job.url) == (
        "Robotics Intern", "Gothenburg", "https://jobs.lever.co/acme/a1")
    assert parse_posting(job.text).sections["requirements"] == [
        "Student in mechatronics", "Python", "We offer relocation."]


def test_ashby_skips_unlisted(serve):
    serve({"api.ashbyhq.com/posting-api/job-board/acme": "ashby.json"})
    listings, _ = sources.fetch_listings(parse_line("https://jobs.ashbyhq.com/acme"))
    assert [l.title for l in listings] == ["Test Engineer"]


def test_recruitee(serve):
    serve({"acme.recruitee.com/api/offers": "recruitee.json"})
    (job,), _ = sources.fetch_listings(parse_line("https://acme.recruitee.com/"))
    assert (job.title, job.country) == ("Mechanical Engineer", "Sweden")
    assert parse_posting(job.text).sections["requirements"] == ["CAD and simulation"]


def test_personio(serve):
    serve({"acme.jobs.personio.de/xml": "personio.xml"})
    (job,), _ = sources.fetch_listings(parse_line("https://acme.jobs.personio.de/"))
    assert (job.title, job.location, job.url) == (
        "Systems Engineer", "Bremen", "https://acme.jobs.personio.de/job/42")
    sections = parse_posting(job.text).sections
    assert sections["responsibilities"] == ["Run verification campaigns."]
    assert sections["requirements"] == ["Python, validation."]


def test_table_site_without_table_falls_back_to_links(serve):
    serve({"startup.example/careers": "links_page.html"})
    listings, source = sources.fetch_listings(parse_line("x https://startup.example/careers"))
    assert source == "links"
    assert [l.title for l in listings] == ["Flight Software Engineer", "Thermal Engineer"]
