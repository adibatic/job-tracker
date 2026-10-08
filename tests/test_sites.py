from pathlib import Path

import pytest

from job_tracker.sites import detect, load_sites, parse_line, select


@pytest.mark.parametrize("url, expected", [
    ("https://spaceco.example/career/job-opportunities/", ("table", "")),
    ("https://boards.greenhouse.io/acme", ("greenhouse", "acme")),
    ("https://job-boards.greenhouse.io/acme/jobs/123", ("greenhouse", "acme")),
    ("https://jobs.lever.co/acme", ("lever", "acme")),
    ("https://jobs.ashbyhq.com/orbitco", ("ashby", "orbitco")),
    ("https://acme.recruitee.com/", ("recruitee", "acme")),
    ("https://acme.jobs.personio.de/", ("personio", "acme")),
])
def test_detect(url, expected):
    assert detect(url) == expected


def test_line_with_name_and_options(tmp_path):
    site = parse_line("startup  https://startup.example/careers  pattern=/careers/.+ render=yes",
                      data_root=tmp_path)
    assert (site.name, site.source, site.pattern, site.render) == (
        "startup", "table", "/careers/.+", True)
    assert site.db == tmp_path / "startup" / "jobs.db"


def test_name_defaults_to_board_or_domain():
    assert parse_line("https://jobs.lever.co/acme").name == "acme"
    assert parse_line("https://www.spaceco.example/career/").name == "spaceco"


def test_comments_and_blank_lines_are_skipped():
    assert parse_line("   ") is None
    assert parse_line("# spaceco https://spaceco.example") is None


@pytest.mark.parametrize("line, message", [
    ("spaceco spaceco.example", "no url"),
    ("a b https://x.example", "expected 'name url"),
    ("bad/name https://x.example", "may only contain"),
    ("x https://x.example colour=blue", "unknown option"),
    ("x https://x.example source=myspace", "source must be one of"),
])
def test_bad_lines_explain_themselves(line, message):
    with pytest.raises(ValueError, match=message):
        parse_line(line)


def test_feed_without_board_is_rejected(tmp_path):
    f = tmp_path / "sites.txt"
    f.write_text("x https://careers.example source=lever\n")
    with pytest.raises(ValueError, match="needs board="):
        load_sites(f, tmp_path)


def test_duplicate_names_are_rejected(tmp_path):
    f = tmp_path / "sites.txt"
    f.write_text("a https://one.example\na https://two.example\n")
    with pytest.raises(ValueError, match="used twice"):
        load_sites(f, tmp_path)


def test_select_by_name(tmp_path):
    f = tmp_path / "sites.txt"
    f.write_text("a https://one.example\nb https://two.example\n")
    sites = load_sites(f, tmp_path)
    assert [s.name for s in select(sites, ["b"])] == ["b"]
    assert [s.name for s in select(sites, [])] == ["a", "b"]
    with pytest.raises(ValueError, match="unknown site"):
        select(sites, ["c"])


def test_example_sites_file_is_valid():
    config = Path(__file__).parents[1] / "config"
    assert load_sites(config / "sites.example.txt") == []      # only commented examples


def test_missing_sites_file_explains_what_to_do(tmp_path):
    with pytest.raises(ValueError, match="Copy sites.example.txt"):
        load_sites(tmp_path / "sites.txt", tmp_path)
