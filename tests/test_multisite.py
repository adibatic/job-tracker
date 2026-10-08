"""fetch / report / changes across several sites, each in its own data folder."""

from pathlib import Path

import pytest

from job_tracker import http, storage
from job_tracker.classify import EXAMPLE_PROFILE
from job_tracker.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def _posting_page(name: str) -> str:
    lines = (FIXTURES / name).read_text(encoding="utf-8").splitlines()
    return "<html><body>" + "".join(f"<p>{l}</p>" for l in lines) + "</body></html>"


@pytest.fixture
def web(monkeypatch):
    """Two fake sites: a table page with three postings, and a Lever feed."""
    pages = {
        "spaceco.example/career/job-opportunities/ground": _posting_page("ground_ops.txt"),
        "spaceco.example/career/job-opportunities/operations": _posting_page("work_rights.txt"),
        "spaceco.example/career/job-opportunities/flight": _posting_page("graduate_safety.txt"),
        "spaceco.example/career/job-opportunities/": (FIXTURES / "list_page.html").read_text(),
        "api.lever.co/v0/postings/acme": (FIXTURES / "feeds" / "lever.json").read_text(),
    }
    requested = []

    def fake_get(url, timeout=30.0):
        requested.append(url)
        for fragment, body in pages.items():
            if fragment in url:
                return body
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(http, "get", fake_get)
    return pages, requested


@pytest.fixture
def setup(tmp_path):
    sites = tmp_path / "sites.txt"
    sites.write_text("spaceco   https://spaceco.example/career/job-opportunities/\n"
                     "acme  https://jobs.lever.co/acme\n")
    data = tmp_path / "data"
    return ["--sites", str(sites), "--data", str(data),
            "--profile", str(EXAMPLE_PROFILE)], data


def test_each_site_gets_its_own_folder(web, setup, capsys):
    args, data = setup
    assert main(args + ["fetch"]) == 0
    for name in ("spaceco", "acme"):
        assert (data / name / "jobs.db").exists()
        assert list((data / name / "exports").glob("changes-*.md"))
        assert list((data / name / "raw").glob("*/*.txt"))
    out = capsys.readouterr().out
    assert "=== All sites" in out
    assert "spaceco              new   3" in out
    assert "acme                 new   1" in out


def test_feed_postings_are_not_downloaded_again(web, setup):
    _, requested = web
    args, _ = setup
    main(args + ["fetch", "acme"])
    assert requested == ["https://api.lever.co/v0/postings/acme?mode=json"]


def test_fetch_one_site_leaves_the_other_alone(web, setup):
    args, data = setup
    assert main(args + ["fetch", "acme"]) == 0
    assert (data / "acme" / "jobs.db").exists()
    assert not (data / "spaceco").exists()


def test_second_run_reports_per_site_changes(web, setup, capsys):
    pages, _ = web
    args, _ = setup
    main(args + ["fetch"])
    pages["spaceco.example/career/job-opportunities/"] = pages[
        "spaceco.example/career/job-opportunities/"].replace("2026-08-31", "2026-10-31")
    capsys.readouterr()
    main(args + ["fetch"])
    out = capsys.readouterr().out
    assert "## Changed (1)" in out
    assert "closing_date: '2026-08-31' -> '2026-10-31'" in out
    assert "acme                 new   0" in out


def test_report_ranks_across_sites(web, setup, capsys):
    args, _ = setup
    main(args + ["fetch"])
    capsys.readouterr()
    main(args + ["report", "--all", "--top", "10"])
    lines = capsys.readouterr().out.strip().splitlines()
    assert {line.split()[3] for line in lines} == {"spaceco", "acme"}
    scores = [float(line.split()[0]) for line in lines]
    assert scores == sorted(scores, reverse=True)


def test_unknown_site_name_is_an_error(web, setup, capsys):
    args, _ = setup
    assert main(args + ["fetch", "nasa"]) == 1
    assert "unknown site(s): nasa" in capsys.readouterr().err


def test_old_single_site_data_moves_into_its_folder(tmp_path, fixture_text, capsys):
    data = tmp_path / "data"
    storage.connect(data / "jobs.db").close()
    (data / "raw" / "2026-10-08").mkdir(parents=True)
    (data / "exports").mkdir()
    sites = tmp_path / "sites.txt"
    sites.write_text("spaceco https://spaceco.example/career/job-opportunities/\n")

    assert main(["--sites", str(sites), "--data", str(data),
                 "--profile", str(EXAMPLE_PROFILE), "sites"]) == 0
    assert (data / "spaceco" / "jobs.db").exists()
    assert (data / "spaceco" / "raw" / "2026-10-08").is_dir()
    assert not (data / "jobs.db").exists()
    assert "Moved existing data" in capsys.readouterr().out
