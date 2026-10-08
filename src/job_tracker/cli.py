"""Track job postings on N career sites listed in config/sites.txt.

Commands (SITE... limits a command to those sites; default all):

  sites                  list configured sites, how each is read, and their runs
  fetch   [SITE...]      download postings, classify, store a snapshot, then print
                         what is new, reopened, changed, first fetched or removed
                         since that site's previous run
  changes [SITE...]      show the latest change summary again (--run TS: one site)
  runs    [SITE...]      list run timestamps
  report  [SITE...]      rank the latest postings across the sites
  skills  [SITE...]      how many postings mention each skill you want to learn
  rescore [SITE...]      re-classify stored postings; no downloads
  classify FILE...       classify pasted posting texts offline
                         (--site NAME --store also saves them to that site)

Each site's data lives in data/<name>/ (jobs.db, raw/, exports/, manual/).
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

from . import changes, http, storage
from .classify import DEFAULT_PROFILE, classify, load_profile
from .detail import parse_posting
from .listing import Listing
from .sites import DATA_ROOT, DEFAULT_SITES_FILE, Site, load_sites, select


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80]


def migrate_legacy(data_root: Path, sites: list[Site]) -> None:
    """Move data from the single-site layout (data/jobs.db) into data/<site>/."""
    legacy_db = data_root / "jobs.db"
    if not legacy_db.exists() or not sites:
        return
    target = sites[0]
    if target.db.exists():
        print(f"Note: {legacy_db} is from the old single-site layout, but {target.db} "
              "already exists. Leaving both untouched.", file=sys.stderr)
        return
    target.folder.mkdir(parents=True, exist_ok=True)
    for name in ("jobs.db", "raw", "exports", "manual"):
        if (data_root / name).exists():
            shutil.move(str(data_root / name), str(target.folder / name))
    print(f"Moved existing data from {data_root}/ to {target.folder}/ (one folder per site).")


# ---------------------------------------------------------------- fetch

def fetch_site(site: Site, profile: dict, limit: int) -> tuple[int, changes.RunChanges | None]:
    from .fetch import fetch_posting_text
    from .sources import fetch_listings

    print(f"\n=== {site.name}  ({site.url})")
    try:
        listings, source = fetch_listings(site)
    except Exception as exc:
        print(f"  Could not read the list: {exc}", file=sys.stderr)
        return 1, None
    if not listings:
        print("  No postings found. The page may build its list with JavaScript "
              "(add render=yes) or need a pattern= option; see config/sites.txt.",
              file=sys.stderr)
        return 1, None
    if source != site.source:
        print(f"  No job table found; read job links instead (source={source}).")

    con = storage.connect(site.db)
    fetched_at = storage.new_run_time(con)
    raw_dir = site.raw / fetched_at[:10]
    raw_dir.mkdir(parents=True, exist_ok=True)
    site.manual.mkdir(parents=True, exist_ok=True)
    # Record everything listed, even with --limit, so skipped postings are not
    # reported as removed next time.
    storage.record_run(con, fetched_at, listings)

    total = len(listings)
    if limit:
        listings = listings[:limit]
    n = len(listings)
    downloads = sum(1 for l in listings if not l.text)
    eta = f" (about {downloads * http.DELAY_SECONDS / 60:.0f} min)" if downloads else ""
    print(f"  {total} postings listed; processing {n}{eta}. "
          "Ctrl-C stops early and still prints the summary.")

    failures = done = 0
    interrupted = False
    try:
        for i, listing in enumerate(listings, 1):
            try:
                text = listing.text or fetch_posting_text(listing.url, render=site.render)
            except Exception as exc:  # one bad page should not stop the run
                failures += 1
                print(f"  [{i:>3}/{n}]  FAILED  {listing.title}: {exc}", file=sys.stderr)
                continue
            (raw_dir / f"{slug(listing.title)}.txt").write_text(text, encoding="utf-8")
            posting = parse_posting(text)
            verdict = classify(text, posting, profile, title=listing.title)
            storage.save(con, listing, posting, verdict, text, fetched_at)
            done += 1
            print(f"  [{i:>3}/{n}]  {verdict.score:5.1f}  {verdict.eligibility:18}  "
                  f"{verdict.seniority:11}  {listing.title}")
    except KeyboardInterrupt:
        interrupted = True
        print(f"\n  Stopped after {done} of {n}. Postings not fetched still count as "
              "listed, so they will not show as removed next time.")

    stamp = fetched_at[:16].replace(":", "")
    report = site.exports / f"report-{stamp}.csv"
    storage.export_csv(storage.latest(con), report)
    result = changes.compare(con, fetched_at)
    changes_file = site.exports / f"changes-{stamp}.md"
    changes_file.write_text(changes.to_text(result), encoding="utf-8")
    print()
    print(changes.to_text(result))
    print(f"  Report: {report}\n  Changes: {changes_file}")
    if interrupted:
        raise KeyboardInterrupt
    return (1 if n and failures == n else 0), result


def cmd_fetch(args) -> int:
    profile = load_profile(args.profile)
    status = 0
    results: list[tuple[str, changes.RunChanges]] = []
    try:
        for site in args.selected:
            code, result = fetch_site(site, profile, args.limit)
            status = max(status, code)
            if result is not None:
                results.append((site.name, result))
    except KeyboardInterrupt:
        print("\nStopped. Sites after this one were not fetched.")
        status = 130
    if len(args.selected) > 1:
        print("\n=== All sites")
        for name, r in results:
            print(f"  {name:20} new {len(r.new):3}   reopened {len(r.reopened):3}   "
                  f"changed {len(r.changed):3}   first fetched {len(r.first):3}   "
                  f"removed {len(r.removed):3}")
    return status


# ---------------------------------------------------------------- read-only

def cmd_sites(args) -> int:
    for site in args.selected:
        runs = len(storage.run_times(storage.connect(site.db))) if site.db.exists() else 0
        board = f" board={site.board}" if site.board else ""
        extra = (f" pattern={site.pattern}" if site.pattern else "") + \
                (" render=yes" if site.render else "")
        print(f"{site.name:20} {site.source:10}{board}{extra}  runs: {runs}")
        print(f"{'':20} {site.url}")
        print(f"{'':20} {site.folder}")
    if not args.selected:
        print(f"No sites configured. Add lines to {args.sites}.")
    return 0


def _existing(sites: list[Site]) -> list[Site]:
    found = [s for s in sites if s.db.exists()]
    if not found:
        print("No data yet. Run 'fetch' first.")
    return found


def cmd_changes(args) -> int:
    if args.run and len(args.selected) != 1:
        print("--run needs exactly one site, e.g. 'changes <site> --run <timestamp>'.",
              file=sys.stderr)
        return 1
    status = 0
    for site in _existing(args.selected):
        print(f"=== {site.name}")
        try:
            print(changes.to_text(changes.compare(storage.connect(site.db), args.run)))
        except LookupError as exc:
            print(exc, file=sys.stderr)
            status = 1
    return status


def cmd_runs(args) -> int:
    for site in _existing(args.selected):
        print(f"=== {site.name}")
        con = storage.connect(site.db)
        for r in con.execute("SELECT fetched_at, n_listed FROM runs ORDER BY fetched_at"):
            print(f"  {r['fetched_at']}  {r['n_listed']:4} listed")
    return 0


def cmd_report(args) -> int:
    rows = []
    sites = _existing(args.selected)
    if not sites:
        return 0
    for site in sites:
        rows += [(site.name, r) for r in storage.latest(storage.connect(site.db))]
    if not args.all:
        rows = [(n, r) for n, r in rows if r["eligibility"] != "not_eligible"]
    rows.sort(key=lambda x: -(x[1]["score"] or 0))
    for name, r in rows[: args.top]:
        print(f"{r['score']:5.1f}  {r['eligibility']:18} {r['seniority']:11} {name:10} "
              f"{r['title']}  [{r['location'] or '?'}, closes {r['closing_date'] or '?'}]")
    if not rows:
        print("Nothing to show.")
    return 0


def cmd_skills(args) -> int:
    counts: dict[str, int] = {}
    for site in _existing(args.selected):
        for skill, count in storage.skill_frequency(storage.connect(site.db)):
            counts[skill] = counts.get(skill, 0) + count
    for skill, count in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"{count:4}  {skill}")
    return 0


# ---------------------------------------------------------------- re-classify

def cmd_rescore(args) -> int:
    profile = load_profile(args.profile)
    for site in _existing(args.selected):
        con = storage.connect(site.db)
        rows = con.execute("SELECT url, fetched_at, title, text FROM postings").fetchall()
        for r in rows:
            posting = parse_posting(r["text"])
            verdict = classify(r["text"], posting, profile, title=r["title"] or "")
            storage.update_verdict(con, r["url"], r["fetched_at"], posting, verdict)
        con.commit()
        print(f"{site.name}: re-classified {len(rows)} stored snapshots.")
    return 0


def cmd_classify(args) -> int:
    if args.store and not args.site:
        print("--store needs --site NAME (which site's data to save into).", file=sys.stderr)
        return 1
    try:
        site = select(args.all_sites, [args.site])[0] if args.site else None
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    missing = [p for p in args.files if not Path(p).is_file()]
    if missing:
        print(f"File not found: {', '.join(missing)}. Paste a posting's text into a "
              "file (e.g. data/<site>/manual/some-role.txt) and pass that path.",
              file=sys.stderr)
        return 1
    profile = load_profile(args.profile)
    con = storage.connect(site.db) if args.store else None
    for path in args.files:
        text = Path(path).read_text(encoding="utf-8")
        title = next((ln.strip() for ln in text.splitlines()
                      if ln.strip() and ln.strip().lower() != "job opportunity"), path)
        posting = parse_posting(text)
        verdict = classify(text, posting, profile, title=title)
        print(f"{path}")
        print(f"  eligibility : {verdict.eligibility} {verdict.reasons or ''}")
        print(f"  seniority   : {verdict.seniority}")
        print(f"  languages   : {posting.languages_required}")
        print(f"  have skills : {verdict.have_hits}")
        print(f"  to learn    : {verdict.learn_hits}")
        print(f"  score       : {verdict.score}")
        if con is not None:
            listing = Listing(title=title, location=posting.work_location, country="",
                              closing_date=posting.deadline, url=f"file:{Path(path).name}")
            storage.save(con, listing, posting, verdict, text, storage.now())
    return 0


# ---------------------------------------------------------------- wiring

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="job-tracker", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sites", type=Path, default=DEFAULT_SITES_FILE,
                        help="file listing the career sites (default config/sites.txt)")
    parser.add_argument("--data", type=Path, default=DATA_ROOT,
                        help="folder holding one sub-folder per site (default data/)")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    sub = parser.add_subparsers(dest="command", required=True)

    def command(name, func, help_text, sites=True):
        p = sub.add_parser(name, help=help_text)
        if sites:
            p.add_argument("site_names", nargs="*", metavar="SITE")
        p.set_defaults(func=func)
        return p

    command("sites", cmd_sites, "list configured sites")
    p = command("fetch", cmd_fetch, "download, classify and store postings")
    p.add_argument("--limit", type=int, default=0, help="only the first N postings per site")
    p = command("changes", cmd_changes, "changes in the latest run (or --run) per site")
    p.add_argument("--run", default=None, help="run timestamp from 'runs' (one site only)")
    command("runs", cmd_runs, "list runs per site")
    p = command("report", cmd_report, "rank the latest postings across sites")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--all", action="store_true", help="include not_eligible postings")
    command("skills", cmd_skills, "count learn-skills across sites")
    command("rescore", cmd_rescore, "re-classify stored postings")
    p = command("classify", cmd_classify, "classify pasted posting texts", sites=False)
    p.add_argument("files", nargs="+")
    p.add_argument("--site", default=None, help="site to store into (with --store)")
    p.add_argument("--store", action="store_true", help="also save to the site's database")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.all_sites = load_sites(args.sites, args.data)
        args.selected = select(args.all_sites, getattr(args, "site_names", None))
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1
    migrate_legacy(args.data, args.all_sites)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
