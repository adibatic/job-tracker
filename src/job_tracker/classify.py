"""Score a posting against your profile (config/profile.json).

Three independent judgements:
  eligibility  "not_eligible" if an excluding phrase appears (citizenship,
               clearance, export control); "check_language" if a required
               language is not one of yours (or the posting is in Swedish);
               "check_requirements" if a work-rights phrase appears (right to
               work, work permit, nationality); otherwise "eligible".
  seniority    "graduate", "experienced" or "unclear", from the title plus the
               Requirements and Responsibilities sections.
  score        have-skill hits count 1, learn-skill hits count 0.5,
               graduate roles get +2, experienced roles get -2.
Eligibility reads the full text; seniority and skills read only what the job
asks for, so company boilerplate ("more than 50 years of experience",
"rocket and balloon systems") does not count for every posting.
The score only ranks; you still read the top postings yourself.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .detail import Posting

CONFIG = Path(__file__).resolve().parents[2] / "config"
EXAMPLE_PROFILE = CONFIG / "profile.example.json"
# Your own profile stays off GitHub; without it the example is used.
DEFAULT_PROFILE = CONFIG / "profile.json" if (CONFIG / "profile.json").exists() else EXAMPLE_PROFILE


@dataclass
class Verdict:
    eligibility: str
    reasons: list[str]
    seniority: str
    have_hits: list[str]
    learn_hits: list[str]
    score: float


def load_profile(path: Path = DEFAULT_PROFILE) -> dict:
    with open(path, encoding="utf-8") as f:
        profile = json.load(f)
    return {k: [s.lower() for s in v] if isinstance(v, list) else v
            for k, v in profile.items() if not k.startswith("_")}


def mentions(phrase: str, text: str) -> bool:
    """Whole-word match; a trailing * matches any word ending (robot* -> robotics)."""
    if phrase.endswith("*"):
        pattern = rf"(?<!\w){re.escape(phrase[:-1])}\w*"
    else:
        pattern = rf"(?<!\w){re.escape(phrase)}(?!\w)"
    return re.search(pattern, text) is not None


def hits(phrases: list[str], text: str) -> list[str]:
    return [p for p in phrases if mentions(p, text)]


def _flat(text: str) -> str:
    return " ".join(text.lower().split())


def classify(text: str, posting: Posting, profile: dict, title: str = "") -> Verdict:
    lower = _flat(text)

    reasons = hits(profile["excluding_phrases"], lower)
    missing_languages = [lang for lang in posting.languages_required
                         if lang not in profile["languages"]]
    checks = hits(profile.get("check_phrases", []), lower)
    if reasons:
        eligibility = "not_eligible"
    elif missing_languages:
        eligibility = "check_language"
        reasons = [f"requires {lang}" for lang in missing_languages]
    elif checks:
        eligibility = "check_requirements"
        reasons = checks
    else:
        eligibility = "eligible"

    asked = posting.sections.get("requirements", []) + posting.sections.get("responsibilities", [])
    asked_text = _flat(" ".join(asked)) if asked else lower
    seniority_text = _flat(title) + " " + asked_text

    graduate = bool(hits(profile["graduate_phrases"], seniority_text))
    experienced = (bool(hits(profile["experienced_phrases"], seniority_text))
                   or (posting.years_experience or 0) >= 3)
    if graduate and not experienced:
        seniority = "graduate"
    elif experienced:
        seniority = "experienced"
    else:
        seniority = "unclear"

    have_hits = hits(profile["have_skills"], asked_text)
    learn_hits = hits(profile["learn_skills"], asked_text)
    score = len(have_hits) + 0.5 * len(learn_hits)
    score += {"graduate": 2.0, "experienced": -2.0}.get(seniority, 0.0)

    return Verdict(eligibility, reasons, seniority, have_hits, learn_hits, score)
