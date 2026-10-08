"""Store every run as a dated snapshot in SQLite, and export CSV reports.

Three tables:
  runs          one row per fetch run
  run_listings  which postings the careers page listed in each run, so a
                posting whose page failed to download is not taken as removed
  postings      one row per (posting URL, fetch time) with text and verdict
Repeated runs build a history: what is new, what disappeared, what changed,
and which skills keep coming back.
"""

import csv
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS postings (
    url            TEXT NOT NULL,
    fetched_at     TEXT NOT NULL,
    title          TEXT,
    location       TEXT,
    country        TEXT,
    closing_date   TEXT,
    contract       TEXT,
    start_date     TEXT,
    requirement    TEXT,
    deadline       TEXT,
    degree         TEXT,
    languages      TEXT,
    years          INTEGER,
    eligibility    TEXT,
    reasons        TEXT,
    seniority      TEXT,
    have_hits      TEXT,
    learn_hits     TEXT,
    score          REAL,
    requirements   TEXT,
    responsibilities TEXT,
    text           TEXT,
    PRIMARY KEY (url, fetched_at)
);
CREATE TABLE IF NOT EXISTS runs (
    fetched_at     TEXT PRIMARY KEY,
    n_listed       INTEGER
);
CREATE TABLE IF NOT EXISTS run_listings (
    fetched_at     TEXT NOT NULL,
    url            TEXT NOT NULL,
    title          TEXT,
    location       TEXT,
    country        TEXT,
    closing_date   TEXT,
    PRIMARY KEY (fetched_at, url)
);
"""

REPORT_COLUMNS = ["score", "eligibility", "seniority", "title", "location", "country",
                  "closing_date", "start_date", "languages", "reasons", "have_hits",
                  "learn_hits", "url", "fetched_at"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_run_time(con: sqlite3.Connection) -> str:
    """Now, or one second after the latest run if that is not earlier.

    Run times are the key that separates runs, so two runs started within the
    same second must still get different times.
    """
    t = datetime.now(timezone.utc).replace(microsecond=0)
    last = con.execute("SELECT MAX(fetched_at) FROM runs").fetchone()[0]
    if last:
        last_t = datetime.fromisoformat(last)
        if t <= last_t:
            t = last_t + timedelta(seconds=1)
    return t.isoformat(timespec="seconds")


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def record_run(con: sqlite3.Connection, fetched_at: str, listings) -> None:
    """Remember which postings the careers page showed in this run."""
    con.execute("INSERT OR REPLACE INTO runs VALUES (?, ?)", (fetched_at, len(listings)))
    con.executemany(
        "INSERT OR REPLACE INTO run_listings VALUES (?,?,?,?,?,?)",
        [(fetched_at, l.url, l.title, l.location, l.country, l.closing_date) for l in listings],
    )
    con.commit()


def run_times(con: sqlite3.Connection) -> list[str]:
    """All run timestamps, oldest first."""
    return [r[0] for r in con.execute("SELECT fetched_at FROM runs ORDER BY fetched_at")]


def run_listings(con: sqlite3.Connection, fetched_at: str) -> dict[str, sqlite3.Row]:
    rows = con.execute("SELECT * FROM run_listings WHERE fetched_at = ?", (fetched_at,))
    return {r["url"]: r for r in rows}


def urls_seen_before(con: sqlite3.Connection, fetched_at: str) -> set[str]:
    rows = con.execute("SELECT DISTINCT url FROM run_listings WHERE fetched_at < ?", (fetched_at,))
    return {r[0] for r in rows}


def snapshot(con: sqlite3.Connection, url: str, at: str, before: bool = False):
    """The posting snapshot taken in run `at`, or the latest one before it."""
    if before:
        return con.execute(
            "SELECT * FROM postings WHERE url = ? AND fetched_at < ? "
            "ORDER BY fetched_at DESC LIMIT 1", (url, at)).fetchone()
    return con.execute(
        "SELECT * FROM postings WHERE url = ? AND fetched_at = ?", (url, at)).fetchone()


def save(con: sqlite3.Connection, listing, posting, verdict, text: str, fetched_at: str) -> None:
    con.execute(
        "INSERT OR REPLACE INTO postings VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            listing.url, fetched_at, listing.title, listing.location, listing.country,
            listing.closing_date, posting.contract, posting.start_date, posting.requirement,
            posting.deadline, posting.degree, json.dumps(posting.languages_required),
            posting.years_experience, verdict.eligibility, json.dumps(verdict.reasons),
            verdict.seniority, json.dumps(verdict.have_hits), json.dumps(verdict.learn_hits),
            verdict.score, json.dumps(posting.sections.get("requirements", [])),
            json.dumps(posting.sections.get("responsibilities", [])), text,
        ),
    )
    con.commit()


def update_verdict(con: sqlite3.Connection, url: str, fetched_at: str, posting, verdict) -> None:
    """Overwrite the parsed fields and verdict of one stored snapshot (used by rescore)."""
    con.execute(
        "UPDATE postings SET contract=?, start_date=?, requirement=?, deadline=?, degree=?, "
        "languages=?, years=?, eligibility=?, reasons=?, seniority=?, have_hits=?, "
        "learn_hits=?, score=?, requirements=?, responsibilities=? "
        "WHERE url=? AND fetched_at=?",
        (
            posting.contract, posting.start_date, posting.requirement, posting.deadline,
            posting.degree, json.dumps(posting.languages_required), posting.years_experience,
            verdict.eligibility, json.dumps(verdict.reasons), verdict.seniority,
            json.dumps(verdict.have_hits), json.dumps(verdict.learn_hits), verdict.score,
            json.dumps(posting.sections.get("requirements", [])),
            json.dumps(posting.sections.get("responsibilities", [])), url, fetched_at,
        ),
    )


def latest(con: sqlite3.Connection) -> list[sqlite3.Row]:
    """The most recent snapshot of each posting, best score first."""
    return con.execute(
        """
        SELECT p.* FROM postings p
        JOIN (SELECT url, MAX(fetched_at) AS t FROM postings GROUP BY url) last
          ON p.url = last.url AND p.fetched_at = last.t
        ORDER BY p.score DESC
        """
    ).fetchall()


def export_csv(rows: list[sqlite3.Row], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(REPORT_COLUMNS)
        for row in rows:
            writer.writerow([row[c] for c in REPORT_COLUMNS])


def skill_frequency(con: sqlite3.Connection) -> list[tuple[str, int]]:
    """How many distinct postings ever mentioned each learn-skill."""
    counts: dict[str, set[str]] = {}
    for row in con.execute("SELECT url, learn_hits FROM postings"):
        for skill in json.loads(row["learn_hits"] or "[]"):
            counts.setdefault(skill, set()).add(row["url"])
    return sorted(((s, len(u)) for s, u in counts.items()), key=lambda x: -x[1])
