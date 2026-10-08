from job_tracker import changes, storage
from job_tracker.classify import EXAMPLE_PROFILE, classify, load_profile
from job_tracker.detail import parse_posting
from job_tracker.listing import Listing

T1, T2, T3 = "2026-10-01T00:00:00+00:00", "2026-11-01T00:00:00+00:00", "2026-12-01T00:00:00+00:00"


def listing(url, closing="2027-01-01", title=None):
    return Listing(title or f"Role {url}", "Northtown (SE)", "Sweden", closing, url)


def run(con, at, postings, listed_only=()):
    """Record a run that listed `postings` (fetched) plus `listed_only` (fetch failed)."""
    listings = [l for l, _ in postings] + list(listed_only)
    storage.record_run(con, at, listings)
    for l, text in postings:
        posting = parse_posting(text)
        storage.save(con, l, posting, classify(text, posting, load_profile(EXAMPLE_PROFILE)), text, at)


def titles(group):
    return [c.title for c in group]


def test_first_run_everything_is_new(tmp_path, fixture_text):
    con = storage.connect(tmp_path / "jobs.db")
    run(con, T1, [(listing("a"), fixture_text("ground_ops.txt"))])
    c = changes.compare(con)
    assert c.previous is None
    assert titles(c.new) == ["Role a"]
    assert not (c.removed or c.changed or c.reopened)


def test_new_removed_and_changed(tmp_path, fixture_text):
    con = storage.connect(tmp_path / "jobs.db")
    ops, grad = fixture_text("ground_ops.txt"), fixture_text("graduate_safety.txt")
    run(con, T1, [(listing("a"), ops), (listing("b"), grad)])
    edited = ops.replace("Submission Deadline: 2026-08-31", "Submission Deadline: 2026-09-30")
    run(con, T2, [(listing("a", closing="2026-09-30"), edited), (listing("c"), grad)])

    c = changes.compare(con)
    assert c.previous == T1
    assert titles(c.new) == ["Role c"]
    assert titles(c.removed) == ["Role b"]
    assert titles(c.changed) == ["Role a"]
    details = c.changed[0].details
    assert "closing_date: '2027-01-01' -> '2026-09-30'" in details
    assert "deadline: '2026-08-31' -> '2026-09-30'" in details


def test_reopened_and_unchanged(tmp_path, fixture_text):
    con = storage.connect(tmp_path / "jobs.db")
    ops, grad = fixture_text("ground_ops.txt"), fixture_text("graduate_safety.txt")
    run(con, T1, [(listing("a"), ops), (listing("b"), grad)])
    run(con, T2, [(listing("a"), ops)])
    run(con, T3, [(listing("a"), ops), (listing("b"), grad)])

    c = changes.compare(con)
    assert titles(c.reopened) == ["Role b"]
    assert not c.new and not c.changed and not c.removed


def test_only_text_edit_is_reported(tmp_path, fixture_text):
    con = storage.connect(tmp_path / "jobs.db")
    ops = fixture_text("ground_ops.txt")
    run(con, T1, [(listing("a"), ops)])
    run(con, T2, [(listing("a"), ops.replace("Strong problem-solving", "Excellent problem-solving"))])
    assert changes.compare(con).changed[0].details == ["posting text edited"]


def test_whitespace_only_edit_is_not_a_change(tmp_path, fixture_text):
    con = storage.connect(tmp_path / "jobs.db")
    ops = fixture_text("ground_ops.txt")
    run(con, T1, [(listing("a"), ops)])
    run(con, T2, [(listing("a"), ops.replace("\n", "\n\n"))])
    assert not changes.compare(con).any


def test_failed_download_is_not_removed(tmp_path, fixture_text):
    con = storage.connect(tmp_path / "jobs.db")
    grad = fixture_text("graduate_safety.txt")
    run(con, T1, [(listing("a"), grad)])
    run(con, T2, [], listed_only=[listing("a")])       # page listed it, fetch failed
    c = changes.compare(con)
    assert not c.removed and not c.changed


def test_compare_an_older_run(tmp_path, fixture_text):
    con = storage.connect(tmp_path / "jobs.db")
    grad = fixture_text("graduate_safety.txt")
    run(con, T1, [(listing("a"), grad)])
    run(con, T2, [(listing("a"), grad), (listing("b"), grad)])
    run(con, T3, [(listing("a"), grad)])
    assert titles(changes.compare(con, T2).new) == ["Role b"]
    assert titles(changes.compare(con, T3).removed) == ["Role b"]


def test_summary_text(tmp_path, fixture_text):
    con = storage.connect(tmp_path / "jobs.db")
    run(con, T1, [(listing("a"), fixture_text("graduate_safety.txt"))])
    text = changes.to_text(changes.compare(con))
    assert "first run" in text
    assert "## New (1)" in text
    assert "[check_language] Role a" in text
