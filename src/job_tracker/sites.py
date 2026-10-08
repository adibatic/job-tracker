"""The list of career sites to track (config/sites.txt) and where each one's data goes.

Every site gets its own folder:

    data/<name>/jobs.db        runs, what each run listed, posting snapshots
    data/<name>/raw/<date>/    exact text of every posting fetched that day
    data/<name>/exports/       report-<time>.csv and changes-<time>.md per run
    data/<name>/manual/        posting texts you paste in by hand
"""

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SITES_FILE = ROOT / "config" / "sites.txt"
EXAMPLE_SITES_FILE = ROOT / "config" / "sites.example.txt"
DATA_ROOT = ROOT / "data"

SOURCES = ("table", "links", "greenhouse", "lever", "ashby", "recruitee", "personio")
NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass
class Site:
    name: str
    url: str
    source: str
    board: str = ""
    pattern: str = ""
    render: bool = False
    data_root: Path = DATA_ROOT

    @property
    def folder(self) -> Path:
        return self.data_root / self.name

    @property
    def db(self) -> Path:
        return self.folder / "jobs.db"

    @property
    def raw(self) -> Path:
        return self.folder / "raw"

    @property
    def exports(self) -> Path:
        return self.folder / "exports"

    @property
    def manual(self) -> Path:
        return self.folder / "manual"


def detect(url: str) -> tuple[str, str]:
    """Guess (source, board) from a careers-page address."""
    parts = urlparse(url)
    host = parts.netloc.lower()
    path = [p for p in parts.path.split("/") if p]
    first = path[0] if path else ""
    if host in ("boards.greenhouse.io", "job-boards.greenhouse.io") and first:
        return "greenhouse", first
    if host.endswith("greenhouse.io") and "for" in parts.query:
        board = re.search(r"for=([^&]+)", parts.query)
        return "greenhouse", board.group(1) if board else ""
    if host == "jobs.lever.co" and first:
        return "lever", first
    if host == "jobs.ashbyhq.com" and first:
        return "ashby", first
    if host.endswith(".recruitee.com"):
        return "recruitee", host.split(".")[0]
    if re.search(r"\.jobs\.personio\.(de|com)$", host):
        return "personio", host.split(".")[0]
    return "table", ""


def default_name(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    source, board = detect(url)
    if board:
        return re.sub(r"[^a-z0-9_-]+", "-", board.lower())
    return re.sub(r"[^a-z0-9_-]+", "-", host.split(".")[0])


def parse_line(line: str, data_root: Path = DATA_ROOT) -> Site | None:
    """One line of sites.txt -> Site, or None for blank and comment lines."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    tokens = line.split()
    url = next((t for t in tokens if "://" in t), None)
    if url is None:
        raise ValueError(f"no url (http:// or https://) in: {line}")
    options = dict(t.split("=", 1) for t in tokens if "=" in t and "://" not in t)
    names = [t for t in tokens if t != url and "=" not in t]
    if len(names) > 1:
        raise ValueError(f"expected 'name url [option=value ...]', got: {line}")
    name = names[0] if names else default_name(url)
    if not NAME_PATTERN.match(name):
        raise ValueError(f"site name {name!r} may only contain letters, digits, - and _")

    unknown = set(options) - {"source", "board", "pattern", "render"}
    if unknown:
        raise ValueError(f"unknown option(s) {sorted(unknown)} in: {line}")
    detected_source, detected_board = detect(url)
    source = options.get("source", detected_source)
    if source not in SOURCES:
        raise ValueError(f"source must be one of {', '.join(SOURCES)}, got {source!r}")
    if "pattern" in options:
        re.compile(options["pattern"])           # fail early on a bad regex
    return Site(
        name=name,
        url=url,
        source=source,
        board=options.get("board", detected_board if source == detected_source else ""),
        pattern=options.get("pattern", ""),
        render=options.get("render", "").lower() in ("yes", "true", "1"),
        data_root=data_root,
    )


def load_sites(path: Path = DEFAULT_SITES_FILE, data_root: Path = DATA_ROOT) -> list[Site]:
    if not path.exists():
        raise ValueError(f"{path} not found. Copy {EXAMPLE_SITES_FILE.name} to "
                         f"{path.name} in the same folder and list your career pages there.")
    sites: list[Site] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            site = parse_line(line, data_root)
        except ValueError as exc:
            raise ValueError(f"{path}, line {number}: {exc}") from None
        if site is None:
            continue
        if any(s.name == site.name for s in sites):
            raise ValueError(f"{path}, line {number}: site name {site.name!r} used twice")
        if site.source not in ("table", "links") and not site.board:
            raise ValueError(f"{path}, line {number}: {site.source} needs board=<id>")
        sites.append(site)
    return sites


def select(sites: list[Site], names: list[str] | None) -> list[Site]:
    """The sites named on the command line, or all of them."""
    if not names:
        return sites
    known = {s.name: s for s in sites}
    missing = [n for n in names if n not in known]
    if missing:
        raise ValueError(f"unknown site(s): {', '.join(missing)}. "
                         f"Configured: {', '.join(known) or 'none'}")
    return [known[n] for n in names]
