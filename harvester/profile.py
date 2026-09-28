"""Who is searching: role, experience, cities, skills. One TOML file per person.

The same tool serves a Java developer, a QA engineer and a product manager: only the
profile changes. It drives both the search queries and the post filters.
"""

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# City aliases, so "Gurgaon" in a post matches "Gurugram" in a profile.
CITIES = {
    "bengaluru": ["bengaluru", "bangalore"],
    "hyderabad": ["hyderabad"],
    "chennai": ["chennai"],
    "pune": ["pune"],
    "mumbai": ["mumbai", "navi mumbai", "thane"],
    "gurugram": ["gurugram", "gurgaon"],
    "noida": ["noida", "greater noida"],
    "delhi": ["delhi", "new delhi", "ncr", "delhi ncr"],
    "kolkata": ["kolkata"],
    "ahmedabad": ["ahmedabad"],
    "kochi": ["kochi", "cochin"],
    "trivandrum": ["trivandrum", "thiruvananthapuram"],
    "coimbatore": ["coimbatore"],
    "indore": ["indore"],
    "jaipur": ["jaipur"],
    "chandigarh": ["chandigarh", "mohali"],
    "bhubaneswar": ["bhubaneswar"],
    "mysuru": ["mysuru", "mysore"],
}
_CITY_RX = {city: re.compile(r"\b(" + "|".join(map(re.escape, names)) + r")\b", re.I)
            for city, names in CITIES.items()}
_ANYWHERE = re.compile(r"\b(remote|work from home|wfh|pan india|anywhere in india)\b", re.I)

# How far back to look, in each portal's own terms. Both portals offer these three.
POSTED_WITHIN = {
    "24h": {"label": "last 24 hours", "linkedin": "past-24h", "naukri_days": 1},
    "week": {"label": "last week", "linkedin": "past-week", "naukri_days": 7},
    "month": {"label": "last month", "linkedin": "past-month", "naukri_days": 30},
}

_GENERIC_TITLE_WORDS = {
    "senior", "junior", "sr", "jr", "lead", "head", "associate", "assistant", "trainee",
    "intern", "executive", "manager", "officer", "engineer", "developer", "specialist",
    "analyst", "consultant", "coordinator", "staff", "and", "of", "the",
}

_YRS = r"(?:years?|yrs?)"
_RANGE = re.compile(rf"\b(\d{{1,2}})\s*\+?\s*(?:-|–|to)\s*(\d{{1,2}})\s*\+?\s*{_YRS}", re.I)
_PLUS = re.compile(rf"\b(?:minimum|min\.?|at least)?\s*(\d{{1,2}})\s*\+\s*{_YRS}", re.I)


def experience_ranges(text: str) -> list[tuple[int, int]]:
    """Every '5-8 years', '5 to 8 yrs' or '5+ years' in the text, as (low, high)."""
    ranges = [(int(a), int(b)) for a, b in _RANGE.findall(text)]
    ranges += [(int(a), 99) for a in _PLUS.findall(text)]
    return [(lo, hi) for lo, hi in ranges if lo <= hi]


def cities_in(text: str) -> set[str]:
    return {city for city, rx in _CITY_RX.items() if rx.search(text)}


def canonical_city(name: str) -> str:
    name = name.strip().lower()
    for city, aliases in CITIES.items():
        if name in aliases:
            return city
    return name


@dataclass
class Profile:
    name: str
    role: str
    experience_years: float | None = None
    locations: list[str] = field(default_factory=list)   # empty = anywhere
    skills: list[str] = field(default_factory=list)      # a post must mention one
    exclude_keywords: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)       # every job title to search for
    timeout_minutes: float = 0                            # stop after N minutes; 0 = no limit
    linkedin_queries: list[str] = field(default_factory=list)
    naukri_queries: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=lambda: ["linkedin", "naukri"])
    posted_within: str = "24h"          # "24h", "week" or "month"
    posts_per_search: int = 25

    def __post_init__(self):
        if self.posted_within not in POSTED_WITHIN:
            self.posted_within = "24h"
        self.posts_per_search = max(1, min(int(self.posts_per_search or 25), 200))
        self.timeout_minutes = max(0.0, float(self.timeout_minutes or 0))

    def all_roles(self) -> list[str]:
        """Every job title to search for: `roles` when set, else the single `role`,
        so old one-title profiles keep working unchanged."""
        titles = self.roles or ([self.role] if self.role else [])
        return list(dict.fromkeys(t.strip() for t in titles if t and t.strip()))

    @classmethod
    def load(cls, path: Path) -> "Profile":
        d = tomllib.loads(path.read_text()).get("profile", {})
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    # --- queries -----------------------------------------------------------

    def linkedin_search(self) -> list[str]:
        if self.linkedin_queries:
            return self.linkedin_queries
        roles = self.all_roles()
        q = [f"hiring {r} share resume" for r in roles]
        if roles:
            q.append(f"{roles[0]} hiring email")
        joined = " ".join(roles).lower()
        q += [f"{s} hiring share resume" for s in self.skills[:1] if s.lower() not in joined]
        return list(dict.fromkeys(q))

    def naukri_search(self) -> list[str]:
        return self.naukri_queries or self.all_roles()

    # --- filters -----------------------------------------------------------

    def role_keywords(self) -> list[str]:
        """What a post must mention. Without explicit skills, the role's own words:
        "Sales Executive" -> ["sales executive", "sales"]. Generic words like
        "executive" or "manager" alone would match almost every post, so they are skipped.
        """
        if self.skills:
            return self.skills
        words: list[str] = []
        for r in self.all_roles():
            words.append(r.lower())
            words += [w for w in re.findall(r"[a-z0-9+#.]+", r.lower())
                      if len(w) > 1 and w not in _GENERIC_TITLE_WORDS]
        return list(dict.fromkeys(words))

    def check_experience(self, text: str) -> str | None:
        if self.experience_years is None:
            return None
        ranges = experience_ranges(text)
        if not ranges:
            return None  # the post does not say, so do not guess
        exp = self.experience_years
        # One year of slack either way: "5-8 yrs" is worth a mail at 4 or at 9.
        if any(lo - 1 <= exp <= hi + 1 for lo, hi in ranges):
            return None
        lo, hi = ranges[0]
        return f"experience {lo}+ yrs" if hi == 99 else f"experience {lo}-{hi} yrs"

    def check_location(self, text: str) -> str | None:
        if not self.locations or _ANYWHERE.search(text):
            return None
        found = cities_in(text)
        wanted = {canonical_city(c) for c in self.locations}
        if not found or found & wanted:
            return None
        return "location " + ", ".join(sorted(found))

    def check_post(self, text: str) -> str | None:
        return self.check_experience(text) or self.check_location(text)


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "profile"


def to_toml(p: Profile) -> str:
    def arr(xs):
        return "[" + ", ".join(f'"{x}"' for x in xs) + "]"
    exp = "" if p.experience_years is None else f"experience_years = {p.experience_years:g}\n"
    return (
        "# Search profile. Edit any field; empty lists mean \"no restriction\".\n"
        "[profile]\n"
        f'name = "{p.name}"\n'
        f'role = "{p.role}"\n'
        f"# Every job title to search for. Empty = just the role above.\n"
        f"roles = {arr(p.roles)}\n"
        f"{exp}"
        f"# Cities you would work in. A post naming only other cities is dropped.\n"
        f"locations = {arr(p.locations)}\n"
        f"# A post must mention at least one of these.\n"
        f"skills = {arr(p.skills)}\n"
        f"# A post mentioning any of these is dropped.\n"
        f"exclude_keywords = {arr(p.exclude_keywords)}\n"
        f"# Leave empty to generate queries from role + skills.\n"
        f"linkedin_queries = {arr(p.linkedin_queries)}\n"
        f"naukri_queries = {arr(p.naukri_queries)}\n"
        f"# Portals to search: linkedin, naukri.\n"
        f"sources = {arr(p.sources)}\n"
        f"# How far back to look: 24h, week or month.\n"
        f'posted_within = "{p.posted_within}"\n'
        f"# Posts / jobs read per search. More finds more but takes longer.\n"
        f"posts_per_search = {p.posts_per_search}\n"
        f"# Stop the search after this many minutes and return what was found. 0 = no limit.\n"
        f"timeout_minutes = {p.timeout_minutes:g}\n"
    )
