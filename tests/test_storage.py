import csv

from job_tracker import storage
from job_tracker.classify import EXAMPLE_PROFILE, classify, load_profile
from job_tracker.detail import parse_posting
from job_tracker.listing import Listing


def store(con, text, url, fetched_at):
    posting = parse_posting(text)
    verdict = classify(text, posting, load_profile(EXAMPLE_PROFILE))
    listing = Listing("Role", "Northtown", "Sweden", "2027-01-01", url)
    storage.save(con, listing, posting, verdict, text, fetched_at)


def test_round_trip_and_latest_snapshot(tmp_path, fixture_text):
    con = storage.connect(tmp_path / "jobs.db")
    text = fixture_text("graduate_safety.txt")
    store(con, text, "u1", "2026-10-01T00:00:00+00:00")
    store(con, text, "u1", "2026-11-01T00:00:00+00:00")
    store(con, fixture_text("ground_ops.txt"), "u2", "2026-10-01T00:00:00+00:00")

    rows = storage.latest(con)
    assert [r["url"] for r in rows] == ["u1", "u2"]           # best score first
    assert rows[0]["fetched_at"].startswith("2026-11-01")      # newest snapshot only
    assert rows[0]["text"] == text                             # stored text is exact
    assert con.execute("SELECT COUNT(*) FROM postings").fetchone()[0] == 3


def test_csv_export(tmp_path, fixture_text):
    con = storage.connect(tmp_path / "jobs.db")
    store(con, fixture_text("graduate_safety.txt"), "u1", "2026-10-01T00:00:00+00:00")
    out = tmp_path / "report.csv"
    storage.export_csv(storage.latest(con), out)
    with open(out, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["eligibility"] == "check_language"


def test_skill_frequency_counts_postings_not_snapshots(tmp_path, fixture_text):
    con = storage.connect(tmp_path / "jobs.db")
    text = fixture_text("graduate_safety.txt")
    store(con, text, "u1", "2026-10-01T00:00:00+00:00")
    store(con, text, "u1", "2026-11-01T00:00:00+00:00")
    assert dict(storage.skill_frequency(con))["rocket*"] == 1


def test_runs_in_the_same_second_get_different_times(tmp_path):
    from job_tracker.listing import Listing
    con = storage.connect(tmp_path / "jobs.db")
    first = storage.new_run_time(con)
    storage.record_run(con, first, [Listing("A", "", "", "", "a")])
    second = storage.new_run_time(con)
    assert second > first
