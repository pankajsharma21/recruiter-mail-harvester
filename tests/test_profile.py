from pathlib import Path

from conftest import example
from harvester.profile import Profile, experience_ranges, to_toml

ROOT = Path(__file__).parent.parent
QA = example("qa-engineer")
PM = example("product-manager")


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


def test_multiple_roles_drive_queries_and_keywords():
    p = Profile(name="x", role="Java Developer",
                roles=["Java Developer", "Spring Boot Developer", "Backend Engineer"])
    # One search per title, plus one extra angle on the first.
    assert p.linkedin_search() == [
        "hiring Java Developer share resume",
        "hiring Spring Boot Developer share resume",
        "hiring Backend Engineer share resume",
        "Java Developer hiring email",
    ]
    assert p.naukri_search() == ["Java Developer", "Spring Boot Developer", "Backend Engineer"]
    # A post is kept if it mentions any title's words.
    assert "spring" in p.role_keywords() and "backend" in p.role_keywords()


def test_single_role_still_works_without_roles_list():
    p = Profile(name="x", role="Accountant")
    assert p.all_roles() == ["Accountant"]
    assert p.naukri_search() == ["Accountant"]
    assert p.linkedin_search() == ["hiring Accountant share resume", "Accountant hiring email"]


def test_toml_round_trip(tmp_path):
    p = Profile(name="A", role="Product Manager", experience_years=7, locations=["Noida"],
                skills=["product manager"], exclude_keywords=["project manager"], sources=["naukri"],
                posted_within="week", posts_per_search=40,
                roles=["Product Manager", "Product Owner"], timeout_minutes=5)
    f = tmp_path / "pm.toml"
    f.write_text(to_toml(p))
    assert Profile.load(f) == p


def test_keywords_from_role_for_any_job():
    assert Profile(name="x", role="Sales Executive").role_keywords() == ["sales executive", "sales"]
    assert Profile(name="x", role="Accountant").role_keywords() == ["accountant"]
    assert Profile(name="x", role="Senior HR Manager").role_keywords() == ["senior hr manager", "hr"]


def test_non_it_examples():
    acc = example("accountant")
    assert reason("Hiring Accountant, Tally + GST, 1-3 yrs, Noida. Mail hr@firm.in", acc) is None
    assert reason("Hiring Accountant, 8-10 yrs, Noida", acc) == "experience 8-10 yrs"
    sales = example("sales-executive")
    assert reason("Sales Executive, fresher to 2 yrs, Mumbai, fixed salary", sales) is None
    assert reason("Sales executive, commission only, Mumbai", sales).startswith("excluded keyword")


def test_every_example_profile_loads():
    for path in (ROOT / "examples" / "profiles").glob("*.toml"):
        assert Profile.load(path).role


def test_posted_within_maps_to_each_portal():
    from harvester.profile import POSTED_WITHIN
    from harvester.sources import linkedin, naukri
    assert "past-week" in linkedin.search_url("hiring accountant", POSTED_WITHIN["week"]["linkedin"])
    assert naukri.search_url("Accountant", POSTED_WITHIN["month"]["naukri_days"]).endswith("jobAge=30")
    assert Profile(name="x", role="y").posted_within == "24h"


def test_bad_saved_values_fall_back_safely():
    p = Profile(name="x", role="y", posted_within="year", posts_per_search=5000)
    assert (p.posted_within, p.posts_per_search) == ("24h", 200)


def test_naukri_page_urls():
    from harvester.sources import naukri
    assert naukri.search_url("Sales Executive", 7) == "https://www.naukri.com/sales-executive-jobs?jobAge=7"
    assert naukri.search_url("Sales Executive", 7, 3) == "https://www.naukri.com/sales-executive-jobs-3?jobAge=7"


def test_quotes_and_backslashes_survive_saving(tmp_path):
    # Raw text between quotes broke the TOML, and the person vanished from the screen.
    p = Profile(name='Priya "PJ"', role=r"C\C++ Developer", roles=[r"C\C++ Developer", 'Dev "lead"'],
                skills=["c#", ".net"], exclude_keywords=['"night shift"', "tab\there", "line\nbreak"])
    f = tmp_path / "p.toml"
    f.write_text(to_toml(p))
    assert Profile.load(f) == p


def test_bad_saved_numbers_fall_back(tmp_path):
    f = tmp_path / "p.toml"
    f.write_text('[profile]\nname = "x"\nrole = "y"\ntimeout_minutes = "five"\nposts_per_search = "lots"\n')
    p = Profile.load(f)
    assert p.timeout_minutes == 0 and p.posts_per_search == 25
