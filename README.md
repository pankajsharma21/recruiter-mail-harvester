# Recruiter Mail Harvester

**Collects recruiter email addresses from LinkedIn hiring posts and Naukri job descriptions, filters out the noise, and hands you a clean list of addresses you have never seen before, ready to feed into a mailer.**

Built with Python and Playwright. It runs on your own machine, uses your own browser session, and needs no paid service or API key.

---

## Why this exists

When you are job hunting, recruiters post things like *"Hiring Java developers, share your CV at talent@company.com"* all day on LinkedIn, and some Naukri job descriptions end with an address too. Collecting these by hand every morning means opening dozens of posts, clicking "…more" on each one, copying addresses, and checking which ones you already mailed.

This tool does that loop for you:

```
search queries (config.toml)
        │
        ▼
┌──────────────┐   ┌──────────────┐   ┌───────────────┐   ┌──────────────┐
│  Playwright  │──►│   extract    │──►│    filter     │──►│   SQLite     │──► new_emails.txt
│  (real       │   │  emails +    │   │  role match,  │   │  history:    │    leads.csv
│   Chrome)    │   │  [at]/[dot]  │   │  drop spam /  │   │  only NEW    │
│              │   │  decoding    │   │  US bench /   │   │  addresses   │
│ LinkedIn     │   │              │   │  job seekers  │   │  reported    │
│ Naukri       │   │              │   │               │   │              │
└──────────────┘   └──────────────┘   └───────────────┘   └──────────────┘
```

## Features

- **Two sources**
  - **LinkedIn**: content search, last 24 hours, newest first. Scrolls to load more posts, expands every truncated post, and reads the full text.
  - **Naukri**: job search, opens each listing and reads the job description.
- **Finds obfuscated addresses.** `hr [at] acme [dot] com` becomes `hr@acme.com`. A bare " at " is left alone on purpose, because "hiring at Gurugram" is not an email.
- **Rule-based filtering, fully in config.** A post must mention your role (Java, Spring, …). It is dropped if it matches a labelled pattern: US bench sales (W2/C2C/H1B), outside India, #OpenToWork job seekers, "job support" communities, other stacks. Every dropped address is still saved **with the reason**, so you can audit the rules.
- **Remembers everything.** A local SQLite database records each address once. A daily run only reports addresses that are new, so you never mail the same recruiter twice from this list.
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

# One time: a browser window opens. Sign in to LinkedIn by hand, then close it.
.venv/bin/harvest login

# Every morning:
.venv/bin/harvest run
```

Your password is never typed into, read by, or stored by this tool. You sign in yourself, and only the browser profile keeps the session cookie, in `~/.local/share/recruiter-mail-harvester/profile`, outside the repo.

## Commands

| Command | What it does |
|---|---|
| `harvest login` | Opens Chrome on the LinkedIn login page. Sign in, close the window, and the session is kept. |
| `harvest run` | Runs every query in `config.toml` on every source. Prints a table and appends to `output/<date>/`. |
| `harvest run --sources linkedin --limit 10` | One source only, 10 posts per query. |
| `harvest scan posts.txt` | Extract and filter from a text file (`-` reads stdin). No browser. |
| `harvest export --days 1` | Kept addresses first seen in the last N days, one per line. Pipe it into your mailer. |

## Sample run

A real Naukri run, two queries, 15 job descriptions each (addresses masked here):

```text
$ harvest run --sources naukri --limit 15
[naukri] java developer
  + a*****.br@hcltech.com  (kept)
  + b*****@hexaware.com  (kept)
  + a*****.br@hcltech.com  (kept)
[naukri] spring boot microservices

EMAIL                                  STATUS             SOURCE    AUTHOR
a*****.br@hcltech.com                  NEW                naukri    HCLTech
b*****@hexaware.com                    NEW                naukri    Hexaware Technologies
a*****.br@hcltech.com                  seen before        naukri    HCLTech

3 found · 3 kept · 2 new → output/2026-09-27/new_emails.txt
```

Two things show up in it. Most Naukri JDs carry no address (2 out of 30 here), which is why LinkedIn posts are the main source. And the same recruiter posting two jobs is reported once as `NEW`, then as `seen before`.

The same run with `--headless` stops immediately with a clear message instead of a traceback:

```text
[naukri] java developer
  ! Naukri blocked this browser (Access Denied) - run without --headless
```

Output files:

| File | Contents |
|---|---|
| `output/<date>/new_emails.txt` | One new, kept address per line. This is the list to mail. |
| `output/<date>/leads.csv` | Every address found: `email, new, status, source, author, url, snippet`. `status` is `kept` or the drop reason. |
| `data/leads.db` | SQLite history across all runs (table `leads`). |

`data/` and `output/` are git-ignored: harvested addresses are personal data and should never be committed.

## Configuration

Everything lives in [`config.toml`](config.toml). No code change is needed to retarget the tool at a different role.

```toml
[search]
linkedin_queries = ["hiring java developer share resume", "..."]
naukri_queries   = ["java developer", "spring boot microservices"]
limit = 25          # posts / JDs per query
naukri_days = 1     # Naukri "posted in last N days"

[rules]
role_keywords = ["java", "spring", "microservice", "backend"]

[rules.drop_patterns]            # label = regex; the label is saved as the drop reason
"us staffing"   = '\b(OPT|H1-?B|EAD|C2C|W2)\b|\bUSA\b'
"job seeker"    = '#?open\s?to\s?work'

[rules.lists]
blocked_emails  = []
blocked_domains = []
```

Patterns use word boundaries on purpose. `\bUSA\b` does not match "Virtusa". There is a test for exactly that case.

## Project structure

```
harvester/
├── cli.py            # argparse commands, run loop, CSV / text output
├── browser.py        # persistent Chrome profile via Playwright
├── extract.py        # email regex, [at]/[dot] decoding, junk filtering, snippets
├── filters.py        # Rules: role match, labelled drop patterns, blocklists
├── store.py          # SQLite history, "is this address new?"
└── sources/
    ├── __init__.py   # Post dataclass, Blocked error, polite_pause()
    ├── linkedin.py   # content search → scroll → expand "…more" → posts
    └── naukri.py     # job search → open each JD → description text
tests/                # extraction + filter rules + end-to-end on a fixture post
config.toml
```

Adding a portal means one new file in `sources/` with an async `posts(page, query, limit)` generator that yields `Post` objects. Extraction, filtering, dedup and output are shared.

## Tests

```bash
.venv/bin/pytest -q
```

The tests cover plain and obfuscated addresses, junk rejection (`logo@2x.png`, `noreply@`), dedup, every filter label, the Virtusa/USA word-boundary case, and a full post → lead run on a fixture. No network is needed.

## Things learned while building it

- **Naukri refuses headless Chrome.** Its CDN answers a headless browser with a bare "Access Denied" page. A visible browser gets the normal site. The tool detects that page and says so, instead of reporting "0 jobs".
- **LinkedIn lazy-loads only on real scroll events.** `window.scrollTo()` loads nothing new. Playwright's `mouse.wheel()` does.
- **The address is usually in the truncated part of a post**, so every "…more" button is clicked before reading.
- **Nested list items.** Comments and reshares are list items inside a post, so only the outermost ones count as posts. Otherwise one post is read several times.

## Responsible use

This is a personal job-search helper, not a bulk scraper.

- It reads only pages you could open yourself, in your own logged-in browser, at human speed.
- LinkedIn's terms restrict automated access. Keep the limits low and runs to about once a day. Heavy use can get an account restricted.
- The addresses collected belong to real people. Use them only to apply for the jobs they posted. Do not resell or share them, and do not commit them (the `.gitignore` already prevents it).

## License

MIT
