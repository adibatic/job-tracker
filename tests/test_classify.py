import pytest

from job_tracker.classify import EXAMPLE_PROFILE, classify, load_profile, mentions
from job_tracker.detail import parse_posting


@pytest.fixture
def profile():
    return load_profile(EXAMPLE_PROFILE)


def verdict(text, profile):
    return classify(text, parse_posting(text), profile)


def test_eu_citizenship_excludes(fixture_text, profile):
    v = verdict(fixture_text("ground_ops.txt"), profile)
    assert v.eligibility == "not_eligible"
    assert "eu citizenship" in v.reasons


def test_proven_experience_is_experienced(fixture_text, profile):
    assert verdict(fixture_text("ground_ops.txt"), profile).seniority == "experienced"


def test_international_does_not_count_as_intern(fixture_text, profile):
    # "international environment" in the benefits must not read as "intern".
    assert verdict(fixture_text("ground_ops.txt"), profile).seniority != "graduate"


def test_graduate_role_needing_swedish(fixture_text, profile):
    v = verdict(fixture_text("graduate_safety.txt"), profile)
    assert v.eligibility == "check_language"
    assert v.reasons == ["requires swedish"]
    assert v.seniority == "graduate"
    assert {"trajector*", "dispersion", "rocket*"} <= set(v.learn_hits)
    assert {"python", "simulation*"} <= set(v.have_hits)


def test_company_boilerplate_is_not_a_skill(fixture_text, profile):
    # "rocket and balloon systems" is in the company's About text, not in the job.
    v = verdict(fixture_text("ground_ops.txt"), profile)
    assert "rocket*" not in v.learn_hits
    assert {"tt&c", "leop", "telemetry"} <= set(v.learn_hits)


def test_graduate_role_outranks_experienced(fixture_text, profile):
    grad = verdict(fixture_text("graduate_safety.txt"), profile)
    senior = verdict(fixture_text("ground_ops.txt"), profile)
    assert grad.score > senior.score


@pytest.mark.parametrize("phrase, text, expected", [
    ("intern", "an international team", False),
    ("intern", "summer intern wanted", True),
    ("robot*", "robotics lab", True),
    ("c++", "modern c++ code", True),
    ("git", "digital systems", False),
    ("tt&c", "knowledge of tt&c systems", True),
])
def test_whole_word_matching(phrase, text, expected):
    assert mentions(phrase, text) is expected
