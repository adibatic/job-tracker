from job_tracker.listing import parse_listings


def test_reads_every_row(fixture_text):
    listings = parse_listings(fixture_text("list_page.html"))
    assert [l.title for l in listings] == [
        "Ground Operations Engineer (f/m/d)",
        "Operations and maintenance technician",
        "Flight Safety Engineer – Launch Site",
    ]


def test_columns_and_absolute_urls(fixture_text):
    first = parse_listings(fixture_text("list_page.html"))[0]
    assert first.location == "Westburg (DE)"
    assert first.country == "Germany"
    assert first.closing_date == "2026-08-31"
    assert first.url == ("https://spaceco.example/career/job-opportunities/"
                         "ground-operations-engineer/")


def test_columns_found_by_header_not_position():
    html = """<table>
      <tr><th>Closing date</th><th>Title</th><th>Country</th><th>Location</th></tr>
      <tr><td>2027-01-01</td><td><a href="/x">Role</a></td><td>Sweden</td><td>Northtown</td></tr>
    </table>"""
    (only,) = parse_listings(html)
    assert (only.title, only.location, only.country, only.closing_date) == (
        "Role", "Northtown", "Sweden", "2027-01-01")


def test_page_without_job_table_gives_nothing():
    assert parse_listings("<html><body><p>No openings</p></body></html>") == []


def test_links_page_finds_postings_not_menu_links(fixture_text):
    from job_tracker.listing import parse_links
    html = fixture_text("feeds/links_page.html")
    listings = parse_links(html, base_url="https://startup.example/en/careers")
    assert [l.title for l in listings] == ["Flight Software Engineer", "Thermal Engineer"]
    assert listings[0].url == "https://startup.example/careers/flight-software-engineer"


def test_links_with_a_pattern_only_keep_matches(fixture_text):
    from job_tracker.listing import parse_links
    html = fixture_text("feeds/links_page.html")
    listings = parse_links(html, "https://startup.example/careers", pattern=r"thermal")
    assert [l.title for l in listings] == ["Thermal Engineer"]


def test_nested_posting_addresses_count_as_jobs():
    from job_tracker.listing import _looks_like_job
    page = "https://spaceco.example/career/job-opportunities/"
    assert _looks_like_job("https://spaceco.example/career/job-opportunities/42d0-6bf/", page)
    assert _looks_like_job("https://x.example/job-12345", "https://x.example/")
    assert not _looks_like_job("https://spaceco.example/career/", page)       # parent page
    assert not _looks_like_job("https://x.example/about", "https://x.example/careers")
