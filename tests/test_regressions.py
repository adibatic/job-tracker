"""Bugs found on the first run against a live careers site, kept fixed by tests."""

from job_tracker import changes, storage
from job_tracker.classify import EXAMPLE_PROFILE, classify, load_profile
from job_tracker.cli import main
from job_tracker.detail import parse_posting, written_in_swedish
from job_tracker.listing import Listing


def verdict(text, title=""):
    return classify(text, parse_posting(text), load_profile(EXAMPLE_PROFILE), title=title)


def test_company_history_is_not_an_experience_requirement(fixture_text):
    # "more than 50 years of experience" describes the company, not the job.
    assert parse_posting(fixture_text("graduate_safety.txt")).years_experience is None
    assert verdict(fixture_text("graduate_safety.txt")).seniority == "graduate"


def test_experience_in_requirements_still_counts():
    text = "Requirements\n* At least 5 years of experience in ground operations.\n"
    assert parse_posting(text).years_experience == 5
    assert verdict(text).seniority == "experienced"


def test_thesis_title_marks_graduate():
    text = "Requirements\n* Studying aerospace or physics.\n"
    title = "Master Thesis: Modelling and Predicting Clouds for Satellite Laser Communication"
    assert verdict(text, title=title).seniority == "graduate"


def test_posting_written_in_swedish_needs_swedish(fixture_text):
    text = fixture_text("swedish_network.txt")
    assert written_in_swedish(text)
    v = verdict(text)
    assert v.eligibility == "check_language"
    assert v.reasons == ["requires swedish"]


def test_english_posting_is_not_swedish(fixture_text):
    assert not written_in_swedish(fixture_text("ground_ops.txt"))


def test_work_rights_need_checking(fixture_text):
    v = verdict(fixture_text("work_rights.txt"))
    assert v.eligibility == "check_requirements"
    assert v.reasons == ["right to work"]


def _one_site(tmp_path):
    sites = tmp_path / "sites.txt"
    sites.write_text("spaceco https://spaceco.example/career/job-opportunities/\n")
    return ["--sites", str(sites), "--data", str(tmp_path / "data"),
            "--profile", str(EXAMPLE_PROFILE)]


def test_rescore_updates_stored_verdicts(tmp_path, fixture_text, capsys):
    db = tmp_path / "data" / "spaceco" / "jobs.db"
    con = storage.connect(db)
    text = fixture_text("graduate_safety.txt")
    posting = parse_posting(text)
    wrong = classify(text, posting, load_profile(EXAMPLE_PROFILE))
    wrong.seniority, wrong.score = "experienced", -99.0          # as an old version stored it
    storage.save(con, Listing("Flight Safety Engineer", "Northtown", "Sweden", "", "u1"),
                 posting, wrong, text, "2026-10-01T00:00:00+00:00")
    con.close()

    assert main(_one_site(tmp_path) + ["rescore"]) == 0
    row = storage.connect(db).execute("SELECT seniority, score FROM postings").fetchone()
    assert row["seniority"] == "graduate"
    assert row["score"] > 0


def test_classify_missing_file_is_a_clear_error(tmp_path, capsys):
    assert main(_one_site(tmp_path) + ["classify", "no/such/file.txt"]) == 1
    assert "File not found" in capsys.readouterr().err


def test_unfetched_new_postings_are_one_compact_line(tmp_path, fixture_text):
    con = storage.connect(tmp_path / "jobs.db")
    fetched = Listing("Fetched role", "Northtown", "Sweden", "", "u1")
    skipped = [Listing(f"Skipped {i}", "Northtown", "Sweden", "", f"s{i}") for i in range(3)]
    at = "2026-10-01T00:00:00+00:00"
    storage.record_run(con, at, [fetched, *skipped])
    text = fixture_text("graduate_safety.txt")
    p = parse_posting(text)
    storage.save(con, fetched, p, classify(text, p, load_profile(EXAMPLE_PROFILE)), text, at)

    summary = changes.to_text(changes.compare(con))
    assert "## New (4)" in summary
    assert "- not fetched yet (3): Skipped 0; Skipped 1; Skipped 2" in summary
    assert "s0" not in summary                                   # no link lines for skipped


def test_postings_skipped_earlier_show_when_first_fetched(tmp_path, fixture_text):
    # Run 1 with --limit lists both but fetches only one; run 2 fetches both.
    con = storage.connect(tmp_path / "jobs.db")
    text = fixture_text("graduate_safety.txt")
    p = parse_posting(text)
    a = Listing("Role a", "Northtown", "Sweden", "", "a")
    b = Listing("Role b", "Northtown", "Sweden", "", "b")
    t1, t2 = "2026-10-01T00:00:00+00:00", "2026-11-01T00:00:00+00:00"
    storage.record_run(con, t1, [a, b])
    storage.save(con, a, p, classify(text, p, load_profile(EXAMPLE_PROFILE)), text, t1)
    storage.record_run(con, t2, [a, b])
    for listing in (a, b):
        storage.save(con, listing, p, classify(text, p, load_profile(EXAMPLE_PROFILE)), text, t2)

    c = changes.compare(con)
    assert [ch.title for ch in c.first] == ["Role b"]
    assert not c.new and not c.changed
    assert "## First fetched (1)" in changes.to_text(c)


def test_short_posting_kept_without_a_browser(monkeypatch, fixture_text):
    from job_tracker import fetch, http
    page = "<html><body>" + "".join(
        f"<p>{l}</p>" for l in fixture_text("work_rights.txt").splitlines()) + "</body></html>"
    monkeypatch.setattr(http, "get", lambda url, timeout=30.0: page)
    monkeypatch.setattr(fetch, "playwright_available", lambda: False)
    text = fetch.fetch_posting_text("https://x.example/careers/technician")
    assert "right to work in Australia" in text


def test_empty_page_without_a_browser_explains_how_to_fix(monkeypatch):
    import pytest
    from job_tracker import fetch, http
    monkeypatch.setattr(http, "get", lambda url, timeout=30.0: "<div id=app></div>")
    monkeypatch.setattr(fetch, "playwright_available", lambda: False)
    monkeypatch.setattr(fetch, "_browser_page", lambda url: (_ for _ in ()).throw(
        RuntimeError("needs a browser to render. Install it with: pip install playwright")))
    with pytest.raises(RuntimeError, match="pip install playwright"):
        fetch.fetch_posting_text("https://x.example/careers/spa")
