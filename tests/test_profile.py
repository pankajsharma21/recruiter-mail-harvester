from pathlib import Path

from harvester.cli import load
from harvester.profile import Profile, experience_ranges, to_toml

ROOT = Path(__file__).parent.parent
QA = load(ROOT / "config.toml", "qa-engineer")
PM = load(ROOT / "config.toml", "product-manager")


def reason(text, setup):
    return setup.rules.check_post(text) or setup.profile.check_post(text)


def test_experience_ranges():
    assert experience_ranges("5-8 years, or 5 to 8 yrs, min 3+ years") == [(5, 8), (5, 8), (3, 99)]
    assert experience_ranges("founded in 2012, 500 employees") == []


def test_experience_filter_with_slack():
    p = Profile(name="x", role="QA", experience_years=3)
    assert p.check_experience("QA 2-4 yrs") is None
    assert p.check_experience("QA 4-6 yrs") is None          # one year short is fine
    assert p.check_experience("QA 8-12 years") == "experience 8-12 yrs"
    assert p.check_experience("QA, experience not mentioned") is None


def test_location_filter_and_aliases():
    p = Profile(name="x", role="QA", locations=["Gurugram", "Bengaluru"])
    assert p.check_location("Office in Gurgaon") is None      # alias
    assert p.check_location("Bangalore / Chennai") is None    # any overlap
    assert p.check_location("Hyderabad only") == "location hyderabad"
    assert p.check_location("Hyderabad or remote") is None
    assert p.check_location("No city given") is None


def test_same_post_different_people():
    post = "Hiring QA Engineer (Selenium), 2-4 yrs, Pune. Share CV at qa@corp.in"
    assert reason(post, QA) is None
    assert reason(post, PM) == "no matching role"


def test_qa_is_not_qatar():
    assert reason("Hiring QA Engineer, 3 yrs, Pune", QA) is None
    assert reason("Hiring engineers for Qatar, 3 yrs", QA).startswith("outside india")


def test_generated_queries():
    # The first skill is added as a query only when the role does not already say it.
    assert QA.profile.linkedin_search() == ["hiring QA Engineer share resume", "QA Engineer hiring email"]
    dev = Profile(name="x", role="Backend Developer", skills=["golang"])
    assert dev.linkedin_search()[-1] == "golang hiring share resume"
    assert PM.profile.naukri_search() == ["Product Manager"]


def test_toml_round_trip(tmp_path):
    p = Profile(name="A", role="Product Manager", experience_years=7, locations=["Noida"],
                skills=["product manager"], exclude_keywords=["project manager"])
    f = tmp_path / "pm.toml"
    f.write_text(to_toml(p))
    assert Profile.load(f) == p
