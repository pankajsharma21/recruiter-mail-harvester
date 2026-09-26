from pathlib import Path

from harvester.cli import leads_from, load_config
from harvester.sources import Post

ROOT = Path(__file__).parent.parent
_, RULES = load_config(ROOT / "config.toml")


def reason(text):
    return RULES.check_post(text)


def test_java_hiring_post_is_kept():
    assert reason("Hiring Java developer, Spring Boot, Pune") is None


def test_off_topic_role_dropped():
    assert reason("Hiring React developer") == "no matching role"


def test_us_bench_sales_dropped():
    assert reason("Java developer, W2 only, H1B ok, USA") == "us staffing"


def test_virtusa_is_not_usa():
    assert reason("Java developer at Virtusa, Chennai") is None


def test_job_seeker_dropped():
    assert reason("#OpenToWork Java developer 4 yrs") == "job seeker"


def test_fixture_post_end_to_end():
    text = (ROOT / "tests/fixtures/posts.txt").read_text()
    leads = leads_from(Post("paste", "", "", text), RULES)
    assert [(l.email, l.status) for l in leads] == [
        ("talent.team@acme-tech.in", "kept"),
        ("hr@acme-tech.in", "kept"),
    ]


def test_blocked_domain():
    leads = leads_from(Post("paste", "", "", "Java dev, mail a@example.com"), RULES)
    assert leads[0].status == "blocked domain"
