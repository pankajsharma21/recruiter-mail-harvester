# Recruiter Mail Harvester

**Collects recruiter email addresses from LinkedIn hiring posts and Naukri job descriptions, keeps only the ones that fit *your* role, experience and cities, and hands you a clean list of addresses you have never seen before, ready to feed into a mailer.**

Built with Python and Playwright. It runs on your own machine, uses your own browser session, and needs no paid service or API key. One install serves a Java developer, a QA engineer and a product manager alike: each person has a small profile file, and nothing else changes.

---

## Why this exists

When you are job hunting, recruiters post things like *"Hiring Java developers, 4-7 yrs, Pune, share your CV at talent@company.com"* all day on LinkedIn, and some Naukri job descriptions end with an address too. Collecting these by hand every morning means opening dozens of posts, clicking "…more" on each one, copying addresses, skipping jobs that need 12 years or sit in the wrong city, and checking which recruiters you already mailed.

This tool does that loop for you:

```
profiles/<you>.toml  (role, experience, cities, skills)
        │  generates the search queries
        ▼
┌──────────────┐   ┌──────────────┐   ┌────────────────────┐   ┌──────────────┐
│  Playwright  │──►│   extract    │──►│      filter        │──►│   SQLite     │──► new_emails.txt
│  (your       │   │  emails +    │   │  role / skills     │   │  history:    │    leads.csv
│   Chrome)    │   │  [at]/[dot]  │   │  experience range  │   │  only NEW    │
│              │   │  decoding    │   │  city              │   │  addresses   │
│ LinkedIn     │   │              │   │  spam, US bench,   │   │  reported    │
│ Naukri       │   │              │   │  job seekers       │   │              │
└──────────────┘   └──────────────┘   └────────────────────┘   └──────────────┘
```

## Features

- **Per-person profiles.** Role, years of experience, preferred cities, must-have keywords and "not for me" keywords live in `profiles/<name>.toml`. `harvest init` asks five questions and writes one, so nobody has to learn TOML.
- **Experience filter.** Reads "5-8 years", "5 to 8 yrs" and "3+ years" from the post. A 3-year QA engineer is not shown a "10+ yrs" job, with one year of slack either way. A post that does not say is kept.
- **City filter with aliases.** Gurgaon matches Gurugram and Bangalore matches Bengaluru. "Remote" and "Pan India" always pass. A post that names no city is kept.
- **Two sources**
  - **LinkedIn**: content search, last 24 hours, newest first. Scrolls to load more posts, expands every truncated post, and reads the full text and the author.
  - **Naukri**: job search, opens each listing and reads the job description.
- **Finds obfuscated addresses.** `hr [at] acme [dot] com` becomes `hr@acme.com`. A bare " at " is left alone on purpose, because "hiring at Gurugram" is not an email.
- **Every drop is explained.** Dropped addresses are still saved, with the rule *and the words that triggered it*: `experience 8-12 yrs`, `location hyderabad`, `job seeker: "#OpenToWork"`, `us staffing: "C2C"`. A misfiring rule is obvious at a glance.
- **Remembers everything, per profile.** A local SQLite database records each address once. A daily run reports only new addresses. An address first seen in an off-target post and later in a matching one is promoted, not lost as "seen before".
- **Blocks are detected, not hidden.** A login wall, an expired session, or a CDN "Access Denied" page stops that portal with a clear message instead of silently returning zero results.
- **Polite by default.** Random 2–5 s gaps between page loads, and a real visible browser instead of a flood of HTTP requests.
- **Works offline too.** `harvest scan` extracts and filters addresses from any pasted text: a WhatsApp forward, an email, a copied post.

## Quick start

Needs Python 3.11+ and Google Chrome installed. The installed Chrome is used, so Playwright downloads no browser.

```bash
git clone https://github.com/pankajsharma21/recruiter-mail-harvester.git
cd recruiter-mail-harvester
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'

# 1. Describe what you are looking for (five questions)
.venv/bin/harvest init

# 2. One time: a browser window opens. Sign in to LinkedIn by hand.
#    The window closes by itself once you are in.
.venv/bin/harvest login

# 3. Every morning:
.venv/bin/harvest run -p <your-profile>
```

Your password is never typed into, read by, or stored by this tool. You sign in yourself, and only the tool's own browser profile keeps the session cookie, in `~/.local/share/recruiter-mail-harvester/profile`, outside the repo.

## Profiles

A profile is who is searching. Three ship as examples:

```text
$ harvest profiles
java-developer         Java Developer         5 yrs     any city
product-manager        Product Manager        7 yrs     Gurugram, Noida, Delhi
qa-engineer            QA Engineer            3 yrs     Pune, Bengaluru
```

Creating one for a friend:

```text
$ harvest init
Your name [Me]: Rahul
Role you are looking for (e.g. QA Engineer, Product Manager) [Java Developer]: Data Analyst
Years of experience (blank = don't filter): 2
Cities you would work in, comma separated (blank = anywhere): Noida, Gurgaon
Keywords a post must mention, comma separated [data analyst]: sql, power bi, data analyst
Keywords that mean 'not for me', comma separated: senior

Saved profiles/data-analyst.toml
LinkedIn queries: ['hiring Data Analyst share resume', 'Data Analyst hiring email', 'sql hiring share resume']
Naukri queries:   ['Data Analyst']
Run it with:  harvest run -p data-analyst
```

The file it writes is plain TOML and can be edited any time:

```toml
[profile]
name = "Rahul"
role = "Data Analyst"
experience_years = 2
locations = ["Noida", "Gurgaon"]          # empty = anywhere
skills = ["sql", "power bi", "data analyst"]   # a post must mention one
exclude_keywords = ["senior"]             # a post mentioning any is dropped
linkedin_queries = []                     # empty = generated from role + skills
naukri_queries = []
```

Each profile keeps its own history and output (`data/<profile>/`, `output/<profile>/`), so two people sharing one machine never see each other's "seen before".

## Commands

| Command | What it does |
|---|---|
| `harvest init` | Asks for role, experience, cities and keywords, and writes `profiles/<role>.toml`. |
| `harvest profiles` | Lists profiles. |
| `harvest login` | Opens Chrome on the LinkedIn login page. Sign in, and the window closes itself once you are in. |
| `harvest run -p qa-engineer` | Searches every source with that profile's queries and filters. Without `-p`, uses `default_profile` from `config.toml`. |
| `harvest run --sources linkedin --limit 10` | One source only, 10 posts per query. |
| `harvest scan posts.txt -p qa-engineer` | Extract and filter from a text file (`-` reads stdin). No browser. |
| `harvest export --days 1 -p qa-engineer` | Kept addresses first seen in the last N days, one per line. Pipe it into your mailer. |

## Sample runs

Real runs, addresses masked here.

**The same LinkedIn results, seen through a QA profile** (3 yrs, Pune or Bengaluru). Every drop names its reason:

```text
$ harvest run -p qa-engineer --sources linkedin
Profile: QA example · QA Engineer · 3 yrs · Pune, Bengaluru
...
EMAIL                                  STATUS                             SOURCE    AUTHOR
g*****@gmail.com                       experience 5+ yrs                  linkedin  (recruiter)
s*****@quest-global.com                location hyderabad                 linkedin  (company page)
r*****@helixbeat.com                   location coimbatore, hyderabad     linkedin  (recruiter)
v*****@gmail.com                       experience 5-14 yrs                linkedin  (recruiter)
c*****@gmail.com                       job seeker: "I'm looking"          linkedin  (job seeker)
h*****@lyfngo.com                      experience 0-1 yrs                 linkedin  (recruiter)
s*****@aromacontracting.com            outside india: "UAE"               linkedin  (agency)
l*****@gmail.com                       us staffing: "C2C"                 linkedin
r*****@gmail.com                       NEW                                linkedin  (recruiter)
n*****@gmail.com                       NEW                                linkedin  (recruiter)

31 found · 3 kept · 3 new → output/qa-engineer/2026-09-27/new_emails.txt
```

**Java developer profile** (5 yrs, any city):

```text
$ harvest run -p java-developer --sources linkedin
Profile: Pankaj · Java Developer · 5 yrs · any city
...
m*****@tmtit.com                       experience 12-15 yrs               linkedin  (recruiter)
g*****@gmail.com                       excluded keyword: "Salesforce"     linkedin  (recruiter)
h*****@autobebesys.com                 outside india: "Canada"            linkedin  (recruiter)
h*****@aielconsulting.com              experience 0-2 yrs                 linkedin  (recruiter)
c*****@gmail.com                       training/support: "Job Assistance" linkedin  (community page)
p*****@pnconsultant.co.in              NEW                                linkedin  (recruiter)
...
38 found · 17 kept
```

**Naukri** (two queries, 15 job descriptions each):

```text
$ harvest run --sources naukri --limit 15
[naukri] java developer
  + a*****.br@hcltech.com  (kept)
  + b*****@hexaware.com  (kept)
  + a*****.br@hcltech.com  (kept)
[naukri] spring boot microservices

3 found · 3 kept · 2 new
```

Most Naukri JDs carry no address (2 out of 30 here), which is why LinkedIn posts are the main source. The same run with `--headless` stops at once with a clear message:

```text
[naukri] java developer
  ! Naukri blocked this browser (Access Denied) - run without --headless
```

Output files:

| File | Contents |
|---|---|
| `output/<profile>/<date>/new_emails.txt` | One new, kept address per line. This is the list to mail. |
| `output/<profile>/<date>/leads.csv` | Every address found: `email, new, status, source, author, url, snippet`. `status` is `kept` or the drop reason. |
| `data/<profile>/leads.db` | SQLite history across all runs (table `leads`). |

`data/` and `output/` are git-ignored: harvested addresses are personal data and should never be committed.

## Shared rules (`config.toml`)

Rules that apply to everyone live in [`config.toml`](config.toml):

```toml
default_profile = "java-developer"

[search]
limit = 25          # posts / JDs per query
naukri_days = 1     # Naukri "posted in last N days"

[rules]
# A post with one of these phrases is a job post, even if someone "Open to Work"
# reshared it; labels in soft_drops are skipped for such posts.
hiring_phrase = '\b(?:share|send|mail|forward|drop)\s+(?:your|their|the)?\s*(?:updated\s+)?(?:resume|cv|profile)|interested candidates'
soft_drops = ["job seeker"]

[rules.drop_patterns]            # label = regex; label + matched words become the reason
"us staffing"      = '\b(OPT|H1-?B|EAD|C2C|W2|GC holders?|USC)\b|\bUSA\b|\bUS based\b'
"outside india"    = '\b(Canada|Riyadh|Dubai|Saudi|Qatar|UAE|Pakistan|Karachi|Lahore|Islamabad)\b'
"job seeker"       = '#?open\s?to\s?work|\bI(?:.m| am) (?:actively )?(?:looking|seeking)|seeking (?:a )?referral'
"training/support" = 'job (support|assistance)|interview support|proxy interview|placement guarantee'

[rules.lists]
blocked_emails  = []
blocked_domains = []
```

Patterns use word boundaries on purpose: `\bUSA\b` does not match "Virtusa", and the skill `qa` does not match "Qatar". There are tests for both.

## Project structure

```
harvester/
├── cli.py            # commands, init wizard, run loop, CSV / text output
├── profile.py        # Profile: queries, experience + city filters, TOML writer
├── browser.py        # persistent Chrome profile via Playwright
├── extract.py        # email regex, [at]/[dot] decoding, junk filtering, snippets
├── filters.py        # Rules: skills match, labelled drop patterns, blocklists
├── store.py          # SQLite history, "is this address new?"
└── sources/
    ├── __init__.py   # Post dataclass, Blocked error, polite_pause()
    ├── linkedin.py   # content search → scroll → expand "…more" → posts
    └── naukri.py     # job search → open each JD → description text
profiles/             # one TOML per person
tests/                # extraction, filters, profiles; no network needed
config.toml           # rules shared by every profile
```

Adding a portal means one new file in `sources/` with an async `posts(page, query, limit)` generator that yields `Post` objects. Extraction, filtering, dedup and output are shared.

## Tests

```bash
.venv/bin/pytest -q
```

23 tests. They cover plain and obfuscated addresses, junk rejection (`logo@2x.png`, `noreply@`), experience parsing and slack, city aliases, one post judged differently by a QA and a PM profile, profile TOML round-trips, and every drop label. Two of them reproduce false positives found in live runs: a recruiter post reshared by someone "Open to Work", and "if you are looking for new opportunities" written by a recruiter.

## Things learned while building it

- **Naukri refuses headless Chrome.** Its CDN answers a headless browser with a bare "Access Denied" page. A visible browser gets the normal site. The tool detects that page and says so, instead of reporting "0 jobs".
- **LinkedIn lazy-loads only on real scroll events.** `window.scrollTo()` loads nothing new. Playwright's `mouse.wheel()` does.
- **The address is usually in the truncated part of a post**, so every "…more" button is clicked before reading.
- **Nested list items.** Comments and reshares are list items inside a post, so only the outermost ones count as posts. Otherwise one post is read several times.
- **The avatar link comes first.** A post's first profile link wraps the photo and has no text, so the author is the first profile or company link that does.
- **LinkedIn signs in with client-side navigation**, so waiting for a page-load event after login never fires. The login command polls the URL instead.
- **Showing the matched words paid off immediately.** Two real recruiters were being dropped as "job seekers". The reason column showed the trigger was an "Open to Work" badge on a reshare, which led to the `hiring_phrase` override.

## Responsible use

This is a personal job-search helper, not a bulk scraper.

- It reads only pages you could open yourself, in your own logged-in browser, at human speed.
- LinkedIn's terms restrict automated access. Keep the limits low and runs to about once a day. Heavy use can get an account restricted, and LinkedIn visibly returns fewer results after several searches in a row.
- The addresses collected belong to real people. Use them only to apply for the jobs they posted. Do not resell or share them, and do not commit them (the `.gitignore` already prevents it).

## License

MIT
