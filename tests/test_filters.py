from pathlib import Path

from conftest import example
from harvester.cli import leads_from
from harvester.sources import Post

ROOT = Path(__file__).parent.parent
JAVA = example("java-developer")


def reason(text, setup=JAVA):
    return setup.rules.check_post(text) or setup.profile.check_post(text)


def test_java_hiring_post_is_kept():
    assert reason("Hiring Java developer, Spring Boot, Pune") is None


def test_off_topic_role_dropped():
    assert reason("Hiring React developer") == "no matching role"


def test_us_bench_sales_dropped():
    assert reason("Java developer, W2 only, H1B ok, USA").startswith("us staffing")


def test_virtusa_is_not_usa():
    assert reason("Java developer at Virtusa, Chennai") is None


def test_job_seeker_dropped_with_matched_words():
    assert reason("#OpenToWork Java developer 4 yrs") == 'job seeker: "#OpenToWork"'
    assert reason("I am actively looking for Java roles").startswith("job seeker")


def test_recruiter_inviting_candidates_is_not_a_job_seeker():
    # Real false positive from a live run: recruiters say this too.
    assert reason("Java developer role. If you are looking for new opportunities, share CV") is None


def test_profile_exclude_keywords():
    assert reason("Hiring Java + Salesforce developer").startswith("excluded keyword")


def test_fixture_post_end_to_end():
    text = (ROOT / "tests/fixtures/posts.txt").read_text()
    leads = leads_from(Post("paste", "", "", text), JAVA)
    assert [(l.email, l.status) for l in leads] == [
        ("talent.team@acme-tech.in", "kept"),
        ("hr@acme-tech.in", "kept"),
    ]


def test_blocked_domain():
    leads = leads_from(Post("paste", "", "", "Java dev, mail a@example.com"), JAVA)
    assert leads[0].status == "blocked domain"


def test_reshared_job_post_is_not_a_job_seeker():
    # Live false positive: a recruiter's post reshared by someone "Open to Work".
    post = "Open to Work\nHiring Java developer. Interested candidates can share their updated resume at x@y.in"
    assert reason(post) is None


def test_job_seeker_offering_own_resume_still_dropped():
    assert reason("#OpenToWork Java dev, happy to connect and share my resume").startswith("job seeker")
