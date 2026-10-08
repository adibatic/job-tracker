# Job Tracker

Tracks job postings on any number of career sites. For each site it keeps a
dated snapshot of every run in its own data folder, tells you what is new or
changed since that site's previous run, and ranks all postings against your
profile, so you can pick the 5–10 roles to build toward over the next year.

It answers four questions per posting:

1. **Can I apply?** Citizenship, security clearance, work rights and language.
2. **Is it for a graduate?** Or does it ask for proven or multi-year experience?
3. **What does it ask for?** Skills you have, and skills you would need to learn.
4. **What is different since last time?** New, reopened, changed, first fetched, removed.

## Adding sites: `config/sites.txt`

Your own `config/sites.txt` and `config/profile.json` are never uploaded (see
`.gitignore`), so which companies you track and your profile stay private.
Copy them from the `*.example.*` files on first use.

One career page per line: a short name, the address, and optional settings.

```
# name      url
spaceco     https://spaceco.example/career/job-opportunities/
orbitco     https://jobs.ashbyhq.com/orbitco
acme        https://boards.greenhouse.io/acme
startup     https://startup.example/careers   pattern=/careers/[a-z0-9-]+$
```

The name becomes the data folder (`data/spaceco/`, `data/orbitco/`, ...). Leave it
out and the board id or domain is used.

How each site is read is detected from its address:

| Address looks like | Read as | Posting text |
|---|---|---|
| `boards.greenhouse.io/<id>` | Greenhouse job-board feed (JSON) | included in the feed |
| `jobs.lever.co/<id>` | Lever postings feed (JSON) | included |
| `jobs.ashbyhq.com/<id>` | Ashby job-board feed (JSON) | included |
| `<id>.recruitee.com` | Recruitee offers feed (JSON) | included |
| `<id>.jobs.personio.de` | Personio feed (XML) | included |
| anything else | an HTML table with a Title column; if there is none, the job links on the page | downloaded from each posting page |

Feeds are more reliable than reading web pages, and need one request per site
instead of one per posting. Many companies' careers pages are hosted on one of
these providers even when they sit on the company's own domain: if a careers
page shows a "Powered by Greenhouse/Lever/Ashby/..." note or its job links
point to such an address, use that address in `sites.txt`.

Options, when detection is not enough:

| Option | Use |
|---|---|
| `source=table\|links\|greenhouse\|lever\|ashby\|recruitee\|personio` | force a reader |
| `board=<id>` | the board or company id for a feed, if the address does not show it |
| `pattern=<regex>` | for link pages: only addresses matching this count as postings |
| `render=yes` | the page builds its list with JavaScript (needs Playwright) |

`python -m job_tracker sites` shows how each line was understood. A mistake in
`sites.txt` stops every command with the file name, line number and reason.

## Architecture

```
job-tracker/
├── config/
│   ├── sites.txt           the career sites to track (edit this)
│   └── profile.json        your languages, deal-breakers, skills (edit this)
├── src/job_tracker/
│   ├── sites.py            sites.txt -> Site(name, url, source, options, data folder)
│   ├── sources.py          Site -> Listings: job-board feeds, or table / links pages
│   ├── listing.py          page readers: job table, job links
│   ├── fetch.py            one posting page -> text; browser only when needed
│   ├── http.py             polite fetching: robots.txt, 3 s delay, UTF-8 default
│   ├── detail.py           posting text -> Posting(contract, dates, requirement,
│   │                       degree, languages, years, sections)
│   ├── classify.py         Posting + profile -> Verdict(eligibility, seniority, skills, score)
│   ├── storage.py          SQLite per site: runs, what each run listed, snapshots
│   ├── changes.py          run vs. previous run of the same site
│   └── cli.py              sites | fetch | changes | runs | report | skills | rescore | classify
├── tests/                  pytest, offline; fixtures include sample feeds per provider
└── data/                   created on first run, one folder per site (not committed)
    └── <site>/
        ├── jobs.db         every run and every snapshot of this site
        ├── raw/<date>/     exact text of every posting fetched that day
        ├── exports/        report-<time>.csv, changes-<time>.md per run
        └── manual/         posting texts you paste in by hand
```

Data flow, per site:

```
sites.txt ─sites.py─▶ Site ─sources.py─▶ Listings ─(fetch.py if no text)─▶ text ─detail.py─▶ Posting
                                                                          │                │
                                                                          └─classify.py◀───┘
                                                                                 │
                                    data/<site>/jobs.db ◀─storage.py── Verdict
                                                 │
                         previous run ─changes.py─▶ data/<site>/exports/changes-<time>.md
```

## Setup

```bash
cp config/sites.example.txt config/sites.txt          # then list your career pages
cp config/profile.example.json config/profile.json    # then edit to fit you
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest                      # 82 tests, all offline
```

Optional, only for sites that need `render=yes` or whose posting pages load
their text with JavaScript:

```bash
pip install playwright
playwright install chromium
```

## Usage

Run from the project root with `src` on the path (or `pip install -e .` once,
then use `job-tracker` instead of `python -m job_tracker`). Each line below is a
separate command; run the one you need, not the whole block.

```bash
export PYTHONPATH=src
```

Check your sites:

```bash
python -m job_tracker sites                     # how each line of sites.txt was understood
```

Collect postings:

```bash
python -m job_tracker fetch --limit 3           # first time: a few postings per site
python -m job_tracker fetch                     # every site, then a change summary per site
python -m job_tracker fetch spaceco orbitco     # only these sites
```

See what changed:

```bash
python -m job_tracker changes                   # latest run vs. the one before, per site
python -m job_tracker runs                      # run timestamps per site
python -m job_tracker changes spaceco --run <timestamp>   # an older run of one site
```

Rank and analyse (across all sites, or the ones you name):

```bash
python -m job_tracker report                    # top 10 you may be eligible for
python -m job_tracker report --all --top 30     # include not_eligible
python -m job_tracker report spaceco            # one site only
python -m job_tracker skills                    # learn-skills by number of postings
python -m job_tracker rescore                   # re-classify stored postings, no downloads
```

Use `rescore` after editing `config/profile.json` or updating the code.

A site read from its web pages takes about 3 seconds per posting (the polite
pause): about 4 minutes for ~76 postings. Feed sites take one request.
`fetch` shows `[i/n]` progress; Ctrl-C stops early, saves what was fetched,
prints that site's change summary and skips the remaining sites.

With more than one site, `fetch` ends with a one-line summary per site:

```
=== All sites
  spaceco              new   2   reopened   0   changed   1   first fetched   0   removed   3
  orbitco              new   1   reopened   0   changed   0   first fetched   0   removed   0
```

If a site cannot be read, or for a posting found elsewhere, paste the posting
text into a file (for example `data/spaceco/manual/flight-safety.txt`) and
classify it offline; `--store` saves it into that site's data:

```bash
python -m job_tracker classify data/<site>/manual/<your-file>.txt --site <site> --store
```

Run `fetch` about once a month. Each run adds a snapshot; nothing is overwritten.

### Upgrading from the single-site version

The first command you run moves an existing `data/jobs.db` (with `raw/`,
`exports/` and `manual/`) into the folder of the first site in `sites.txt`,
keeping your history. It does nothing if
that site already has a `jobs.db`.

## How changes are detected

Each site is compared only with its own previous run.

| Status | Meaning |
|---|---|
| New | listed now, never listed in any earlier run |
| Reopened | listed now and in some earlier run, but not in the previous run |
| Changed | listed in both runs, and the title, closing date, deadline, start date, requirement, languages, eligibility or seniority differs; or only the posting text was edited |
| First fetched | listed before, but downloaded for the first time now (skipped earlier by `--limit` or an interrupted run) |
| Removed | listed in the previous run, not now |

The comparison uses what the site *listed*, not which postings downloaded
successfully, so a temporary download failure is not reported as a removal.
`--limit` still records the full list for the same reason. Whitespace-only
edits are ignored. The first run reports everything as new; postings listed
but not downloaded are summarised on one line.

## How a posting is judged

| Output | Rule |
|---|---|
| `not_eligible` | the full text contains an excluding phrase (EU citizenship, security clearance, ...) |
| `check_language` | a language is required that is not in your `languages` list, or the posting is written in Swedish |
| `check_requirements` | a work-rights phrase appears (right to work, work permit, citizenship, nationality, clearance) |
| `eligible` | none of the above |
| `graduate` / `experienced` / `unclear` | graduate phrases (including a "thesis" title) vs. experienced phrases or 3+ years required |
| score | 1 per have-skill, 0.5 per learn-skill, +2 graduate, −2 experienced |

Seniority and skills are read from the title and the requirements and
responsibilities sections only. Companies name these sections differently
("Requirements", "Qualifications", "About you", "What you'll do", ...); the
common names are recognised. Company paragraphs that repeat in every posting
("more than 50 years of experience", "rocket and balloon systems") would
otherwise mark every job as experienced and as about rockets. Experience
figures above 20 years are ignored for the same reason. When a posting has no
recognisable sections, the whole text is used.

Phrases match whole words; a trailing `*` matches any ending (`robot*` matches
robotics), so "intern" does not match "international". The score only orders
the list. Read the top postings yourself.

## What is uploaded to GitHub

| Committed | Kept on your machine (in `.gitignore`) |
|---|---|
| code, tests, README | `data/`: fetched postings, history, reports (company content) |
| `config/sites.example.txt`, `config/profile.example.json` | `config/sites.txt`: the companies you track |
| synthetic test postings in `tests/fixtures/` | `config/profile.json`: your profile |

The test postings are invented ("Example Space Corp") and only mimic the
structure of real ones. Before each commit, `git status` should list no file
under `data/` and neither `config/sites.txt` nor `config/profile.json`.

## Limits

- **Built without access to the live sites.** The table reader was confirmed on
  a live careers site by a real run; the job-board feeds follow each provider's
  public documentation as I know it and are tested against sample responses
  in `tests/fixtures/feeds/`, not against the providers themselves. If a feed
  fails, compare a real response with its sample, fix that function in
  `sources.py`, and update the sample and its test.
- **Link pages are a best guess.** Without a `pattern=`, links whose address
  contains words like `/job`, `/career`, `/position` count as postings. Check
  the first run's list; if it includes menu links or misses postings, add a
  `pattern=` that matches only posting addresses.
- **Text patterns, not understanding.** Unusual wording can be missed, for
  example a citizenship rule phrased in a new way. Add the phrase to
  `excluding_phrases` or `check_phrases` in `profile.json` when you find one,
  then run `rescore`.
- **Be polite.** Low volume, a delay between requests, robots.txt respected.
  Do not lower the delay or run it often.
