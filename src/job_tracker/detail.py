"""Turn one posting page into plain text, and pull structured fields from it.

The posting text has a fixed shape (see tests/fixtures/ground_ops.txt):
a meta line "City (CC)•Country•Contract", key-value lines such as
"Start Date: Q2 2027", and sections headed Description, Requirements,
Responsibilities and Benefits, with one bullet per line.
"""

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

# Heading text (lower case, without a trailing colon) -> canonical section.
# Companies word these differently; the values are the canonical names.
SECTION_HEADINGS = {
    "description": "description", "about the role": "description",
    "about the job": "description", "the role": "description", "job description": "description",
    "requirements": "requirements", "qualifications": "requirements",
    "required qualifications": "requirements", "minimum qualifications": "requirements",
    "basic qualifications": "requirements", "preferred qualifications": "requirements",
    "about you": "requirements", "who you are": "requirements", "your profile": "requirements",
    "what you bring": "requirements", "what we're looking for": "requirements",
    "what we are looking for": "requirements", "skills and experience": "requirements",
    "you have": "requirements", "must have": "requirements", "nice to have": "requirements",
    "responsibilities": "responsibilities", "key responsibilities": "responsibilities",
    "what you'll do": "responsibilities", "what you will do": "responsibilities",
    "your role": "responsibilities", "your tasks": "responsibilities",
    "duties": "responsibilities", "in this role you will": "responsibilities",
    "benefits": "benefits", "what we offer": "benefits", "perks": "benefits",
    "why join us": "benefits",
}

KEY_VALUE_FIELDS = {
    "start_date": r"start date",
    "work_location": r"location",
    "working_hours": r"working hours",
    "requirement": r"requirements?",
    "deadline": r"submission deadline",
}

# Common Swedish function words; a posting full of them is written in Swedish.
SWEDISH_WORDS = {"och", "att", "för", "med", "som", "vi", "du", "är", "på", "av",
                 "till", "har", "inom", "eller", "dig", "oss", "ett", "en"}

# Experience requirements above this are company history, not job requirements
# ("more than 50 years of experience" in a company's standard paragraph).
MAX_YEARS_REQUIRED = 20

LANGUAGES = ("english", "swedish", "german", "french", "spanish", "italian", "norwegian",
             "finnish", "dutch", "japanese", "chinese", "mandarin")


@dataclass
class Posting:
    contract: str = ""
    start_date: str = ""
    work_location: str = ""
    working_hours: str = ""
    requirement: str = ""
    deadline: str = ""
    degree: str = ""
    languages_required: list[str] = field(default_factory=list)
    years_experience: int | None = None
    sections: dict[str, list[str]] = field(default_factory=dict)


def html_to_text(html: str) -> str:
    """Visible page text, one block per line, scripts and styles removed."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    lines = (" ".join(line.split()) for line in soup.get_text("\n").splitlines())
    return "\n".join(line for line in lines if line)


def _lines(text: str) -> list[str]:
    return [line.strip().lstrip("*•-").strip() for line in text.splitlines()]


def split_sections(text: str) -> dict[str, list[str]]:
    """Map each known section to the non-empty lines under its heading(s).

    Several headings can feed one section ("Must have" and "Nice to have" both
    go to requirements); their lines are joined in order.
    """
    sections: dict[str, list[str]] = {}
    current = None
    for line in _lines(text):
        heading = line.lower().replace("\u2019", "'").rstrip(":").strip()
        if heading in SECTION_HEADINGS:
            current = SECTION_HEADINGS[heading]
            sections.setdefault(current, [])
        elif current and line:
            sections[current].append(line)
    return sections


def written_in_swedish(text: str) -> bool:
    words = re.findall(r"[a-zåäö]+", text.lower())
    if len(words) < 30:
        return False
    return sum(w in SWEDISH_WORDS for w in words) / len(words) > 0.08


def parse_posting(text: str) -> Posting:
    """Extract the structured fields of one posting from its plain text."""
    posting = Posting(sections=split_sections(text))
    lines = _lines(text)

    for line in lines:
        if line.count("•") >= 2:
            posting.contract = line.split("•")[-1].strip()
            break

    for name, key in KEY_VALUE_FIELDS.items():
        match = re.search(rf"^\s*{key}\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        if match:
            setattr(posting, name, match.group(1).strip())

    degree = re.search(r"degree in ([^.\n]+)", text, re.IGNORECASE)
    if degree:
        posting.degree = degree.group(1).strip()

    lower = text.lower()
    languages = {lang for lang in LANGUAGES
                 if re.search(rf"(fluen\w*|proficien\w*|command)[^.\n]{{0,60}}\b{lang}\b", lower)
                 or re.search(rf"\b{lang}\b[^.\n]{{0,40}}(is required|required|fluency)", lower)}
    if written_in_swedish(text):
        languages.add("swedish")
    posting.languages_required = sorted(languages)

    # Only the Requirements section states what the job needs.
    asked = " ".join(posting.sections.get("requirements", [])).lower() or lower
    years = [int(y) for y in re.findall(r"(\d+)\s*\+?\s*(?:years|yrs)", asked)]
    years = [y for y in years if y <= MAX_YEARS_REQUIRED]
    if years:
        posting.years_experience = max(years)
    return posting
