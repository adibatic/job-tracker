"""Compare a run with the run before it.

  new        listed now, never listed in any earlier run
  reopened   listed now and in some earlier run, but not in the previous one
  removed    listed in the previous run, not listed now
  changed    listed in both, and a tracked field or the posting text differs
  first      listed before, but downloaded for the first time in this run
             (e.g. skipped by --limit or an interrupted run earlier)

The comparison uses what the careers page listed (run_listings), so a posting
whose own page failed to download is still counted as present.
"""

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field

from . import storage

TRACKED_FIELDS = ("title", "closing_date", "deadline", "start_date", "requirement",
                  "languages", "eligibility", "seniority")


@dataclass
class Change:
    url: str
    title: str
    eligibility: str = ""
    score: float | None = None
    details: list[str] = field(default_factory=list)


@dataclass
class RunChanges:
    current: str
    previous: str | None
    new: list[Change] = field(default_factory=list)
    reopened: list[Change] = field(default_factory=list)
    removed: list[Change] = field(default_factory=list)
    changed: list[Change] = field(default_factory=list)
    first: list[Change] = field(default_factory=list)

    @property
    def any(self) -> bool:
        return bool(self.new or self.reopened or self.removed or self.changed or self.first)


def _digest(text: str | None) -> str:
    return hashlib.sha256(" ".join((text or "").split()).encode()).hexdigest()


def _change(con: sqlite3.Connection, url: str, listing, at: str) -> Change:
    snap = storage.snapshot(con, url, at)
    return Change(
        url=url,
        title=listing["title"],
        eligibility=snap["eligibility"] if snap else "not fetched",
        score=snap["score"] if snap else None,
    )


def field_differences(old: sqlite3.Row, new: sqlite3.Row) -> list[str]:
    details = []
    for name in TRACKED_FIELDS:
        if (old[name] or "") != (new[name] or ""):
            before, after = old[name], new[name]
            if name == "languages":
                before, after = json.loads(before or "[]"), json.loads(after or "[]")
            details.append(f"{name}: {before!r} -> {after!r}")
    if not details and _digest(old["text"]) != _digest(new["text"]):
        details.append("posting text edited")
    return details


def compare(con: sqlite3.Connection, current: str | None = None) -> RunChanges:
    """Changes in run `current` (default: the latest run) against the run before it."""
    times = storage.run_times(con)
    if not times:
        raise LookupError("No runs recorded yet. Run 'fetch' first.")
    current = current or times[-1]
    if current not in times:
        raise LookupError(f"No run at {current}. Known runs: {', '.join(times)}")
    i = times.index(current)
    previous = times[i - 1] if i > 0 else None

    now_listed = storage.run_listings(con, current)
    before_listed = storage.run_listings(con, previous) if previous else {}
    seen_before = storage.urls_seen_before(con, current)
    result = RunChanges(current=current, previous=previous)

    for url, listing in now_listed.items():
        if url not in seen_before:
            result.new.append(_change(con, url, listing, current))
        elif url not in before_listed:
            result.reopened.append(_change(con, url, listing, current))
        else:
            new_snap = storage.snapshot(con, url, current)
            old_snap = storage.snapshot(con, url, current, before=True)
            if new_snap and old_snap:
                details = field_differences(old_snap, new_snap)
                if details:
                    change = _change(con, url, listing, current)
                    change.details = details
                    result.changed.append(change)
            elif new_snap:
                result.first.append(_change(con, url, listing, current))

    for url, listing in before_listed.items():
        if url not in now_listed:
            result.removed.append(Change(url=url, title=listing["title"]))

    for group in (result.new, result.reopened, result.changed, result.first):
        group.sort(key=lambda c: -(c.score or 0))
    return result


def to_text(c: RunChanges) -> str:
    """Plain summary for the terminal and for changes-<date>.md."""
    lines = [f"# Changes in run {c.current}",
             f"Compared with: {c.previous or 'nothing (first run, everything is new)'}", ""]
    if not c.any:
        lines.append("No changes.")
        return "\n".join(lines)
    for heading, group in (("New", c.new), ("Reopened", c.reopened),
                           ("Changed", c.changed), ("First fetched", c.first),
                           ("Removed", c.removed)):
        if not group:
            continue
        fetched = [ch for ch in group if ch.eligibility != "not fetched"]
        unfetched = [ch for ch in group if ch.eligibility == "not fetched"]
        lines.append(f"## {heading} ({len(group)})")
        for ch in fetched:
            score = f"{ch.score:5.1f}  " if ch.score is not None else ""
            tag = f"[{ch.eligibility}] " if ch.eligibility else ""
            lines.append(f"- {score}{tag}{ch.title}")
            lines.extend(f"    - {d}" for d in ch.details)
            lines.append(f"    {ch.url}")
        if unfetched:
            lines.append(f"- not fetched yet ({len(unfetched)}): "
                         + "; ".join(ch.title for ch in unfetched))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
