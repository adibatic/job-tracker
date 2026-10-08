from job_tracker.detail import html_to_text, parse_posting, split_sections


def test_key_value_fields(fixture_text):
    p = parse_posting(fixture_text("ground_ops.txt"))
    assert p.contract == "Permanent"
    assert p.start_date == "Q2 2027"
    assert p.work_location == "Operations Centre, Westburg, Germany"
    assert p.working_hours == "full time, 40h/week"
    assert p.requirement == "EU Citizenship"
    assert p.deadline == "2026-08-31"


def test_degree_and_language(fixture_text):
    p = parse_posting(fixture_text("ground_ops.txt"))
    assert p.degree.startswith("Telecommunications, Aerospace Engineering")
    assert p.languages_required == ["english"]


def test_language_course_is_not_a_requirement(fixture_text):
    # The benefits offer "a German language course"; that must not count.
    assert "german" not in parse_posting(fixture_text("ground_ops.txt")).languages_required


def test_required_swedish_is_detected(fixture_text):
    p = parse_posting(fixture_text("graduate_safety.txt"))
    assert p.languages_required == ["english", "swedish"]


def test_sections(fixture_text):
    sections = split_sections(fixture_text("ground_ops.txt"))
    assert len(sections["requirements"]) == 7
    assert sections["requirements"][-1] == "Fluency in written and spoken English."
    assert len(sections["responsibilities"]) == 4


def test_html_to_text_drops_scripts():
    text = html_to_text("<p>Requirements</p><script>var x = 1;</script><li>Python</li>")
    assert text.splitlines() == ["Requirements", "Python"]
