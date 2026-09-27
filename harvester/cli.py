"""harvest - collect recruiter email addresses from job portals.

    harvest                          open the setup screen (pick or add a person, then search)
    harvest init                     create a search profile (role, experience, cities)
    harvest profiles                 list profiles
    harvest login                    open the browser once and sign in to LinkedIn by hand
    harvest run [-p PROFILE]         search every source, print and save what is new
    harvest scan FILE [-p PROFILE]   extract from pasted text (no browser)
    harvest export --days 1          addresses first seen in the last N days, one per line
"""

import argparse
import asyncio
import csv
import re
import sys
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import extract
from .browser import browser
from .filters import Rules
from .profile import POSTED_WITHIN, Profile, slug, to_toml
from .sources import Blocked, Post, linkedin, naukri
from .store import Lead, Store

ROOT = Path.cwd()
PROFILES_DIR = ROOT / "profiles"


@dataclass
class Setup:
    """Everything a run needs: shared settings plus one person's profile."""
    profile_id: str
    profile: Profile
    search: dict
    rules: Rules

    @property
    def data_dir(self) -> Path:
        return ROOT / "data" / self.profile_id

    @property
    def out_dir(self) -> Path:
        return ROOT / "output" / self.profile_id / date.today().isoformat()


def load_config(path: Path) -> dict:
    return tomllib.loads(path.read_text())


def make_setup(cfg: dict, profile_id: str, profile: Profile) -> Setup:
    rules = cfg.get("rules", {})
    drops = dict(rules.get("drop_patterns", {}))
    if profile.exclude_keywords:
        drops["excluded keyword"] = r"\b(?:" + "|".join(map(re.escape, profile.exclude_keywords)) + r")\b"
    lists = rules.get("lists", {})
    return Setup(profile_id, profile, cfg.get("search", {}), Rules(
        role_keywords=profile.role_keywords(),
        drop_patterns=drops,
        blocked_emails=lists.get("blocked_emails", []),
        blocked_domains=lists.get("blocked_domains", []),
        hiring_phrase=rules.get("hiring_phrase", ""),
        soft_drops=rules.get("soft_drops", []),
    ))


def load(config_path: Path, profile_id: str | None) -> Setup:
    cfg = load_config(config_path)
    last = PROFILES_DIR / ".last"
    profile_id = profile_id or cfg.get("default_profile") or (last.read_text().strip() if last.exists() else "")
    if not profile_id:
        sys.exit("No profile chosen. Run `harvest` to open the setup screen, or pass -p NAME.")
    path = PROFILES_DIR / f"{profile_id}.toml"
    if not path.exists():
        known = ", ".join(sorted(p.stem for p in PROFILES_DIR.glob("*.toml"))) or "none"
        sys.exit(f"No profile '{profile_id}' (known: {known}). Create one with `harvest init` or `harvest`.")
    return make_setup(cfg, profile_id, Profile.load(path))


def leads_from(post: Post, setup: Setup) -> list[Lead]:
    emails = extract.find_emails(post.text)
    if not emails:
        return []
    post_reason = setup.rules.check_post(post.text) or setup.profile.check_post(post.text)
    return [
        Lead(email=e, source=post.source, url=post.url, author=post.author,
             snippet=extract.snippet(post.text, e),
             status=post_reason or setup.rules.check_email(e) or "kept")
        for e in emails
    ]


def save_outputs(leads: list[tuple[Lead, bool]], out: Path) -> list[str]:
    """Append to leads.csv and new_emails.txt; return the new, kept addresses."""
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "leads.csv", "a", newline="") as f:
        w = csv.writer(f)
        if f.tell() == 0:
            w.writerow(["email", "new", "status", "source", "author", "url", "snippet"])
        for lead, new in leads:
            w.writerow([lead.email, new, lead.status, lead.source, lead.author, lead.url, lead.snippet])

    new_kept = list(dict.fromkeys(l.email for l, new in leads if new and l.kept))
    with open(out / "new_emails.txt", "a") as f:
        f.writelines(e + "\n" for e in new_kept)
    return new_kept


def report(leads: list[tuple[Lead, bool]], out: Path) -> None:
    new_kept = save_outputs(leads, out)
    print(f"\n{'EMAIL':38} {'STATUS':34} {'SOURCE':9} AUTHOR")
    for lead, new in leads:
        tag = ("NEW" if new else "seen before") if lead.kept else lead.status
        print(f"{lead.email:38} {tag[:34]:34} {lead.source:9} {lead.author[:30]}")
    kept = sum(l.kept for l, _ in leads)
    print(f"\n{len(leads)} found · {kept} kept · {len(new_kept)} new → {out / 'new_emails.txt'}")


def describe(p: Profile) -> str:
    return (f"{p.name} · {p.role}"
            + (f" · {p.experience_years:g} yrs" if p.experience_years is not None else "")
            + (f" · {', '.join(p.locations)}" if p.locations else " · any city")
            + f" · {POSTED_WITHIN[p.posted_within]['label']}")


async def harvest(page, setup: Setup, store: Store, sources: set[str], limit: int,
                  log=print) -> list[tuple[Lead, bool]]:
    """Search every chosen source with the profile's queries. `log` receives progress lines."""
    found: list[tuple[Lead, bool]] = []
    p = setup.profile
    plan = [
        ("naukri", naukri, p.naukri_search(), {"days": POSTED_WITHIN[p.posted_within]["naukri_days"]}),
        ("linkedin", linkedin, p.linkedin_search(), {"within": POSTED_WITHIN[p.posted_within]["linkedin"]}),
    ]
    for name, source, queries, extra in plan:
        if name not in sources:
            continue
        for q in queries:
            await _maybe_await(log(f"[{name}] {q}"))
            try:
                async for post in source.posts(page, q, limit, **extra):
                    for lead in leads_from(post, setup):
                        found.append((lead, store.record(lead)))
                        await _maybe_await(log(f"  + {lead.email}  ({lead.status})"))
            except Blocked as e:
                # One refusal means the rest of this portal's queries will fail too.
                await _maybe_await(log(f"  ! {e}"))
                break
    return found


async def _maybe_await(x):
    if asyncio.iscoroutine(x):
        await x


async def run(args, setup: Setup, store: Store) -> list[tuple[Lead, bool]]:
    print("Profile:", describe(setup.profile))
    async with browser(headless=args.headless) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        return await harvest(page, setup, store, args.sources,
                             args.limit or setup.profile.posts_per_search)


async def sign_in(page, minutes: int = 10) -> bool:
    """Open LinkedIn's login page and wait until the person has signed in by hand.

    Waiting for the window to be closed let people close it one step too early,
    before the session cookie existed. Poll the URL instead: LinkedIn moves to the
    feed with client-side navigation, which a load-event wait does not see.
    """
    await page.goto("https://www.linkedin.com/login")
    for _ in range(minutes * 60):
        await asyncio.sleep(1)
        if page.is_closed():
            return False
        if "linkedin.com" in page.url and not re.search(r"/(login|checkpoint|authwall|uas)", page.url):
            await asyncio.sleep(3)  # let the session cookie reach disk
            return True
    return False


async def login() -> None:
    async with browser(headless=False) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        print("Sign in inside the browser window. It closes by itself once you are in.")
        if not await sign_in(page):
            sys.exit("Not signed in: the window was closed, or 10 minutes passed. Run `harvest login` again.")
        print("Signed in. Session saved for later runs.")


def ask(prompt: str, default: str = "") -> str:
    shown = f" [{default}]" if default else ""
    return input(f"{prompt}{shown}: ").strip() or default


def split(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


def init() -> None:
    """Interactive profile wizard, so nobody has to learn TOML to use the tool."""
    print("New search profile. Press Enter to accept a [default].\n")
    name = ask("Your name", "Me")
    role = ask("Role you are looking for (e.g. QA Engineer, Product Manager)", "Java Developer")
    exp = ask("Years of experience (blank = don't filter)", "")
    locations = split(ask("Cities you would work in, comma separated (blank = anywhere)", ""))
    skills = split(ask("Keywords a post must mention, comma separated", role.lower()))
    exclude = split(ask("Keywords that mean 'not for me', comma separated", ""))

    profile = Profile(name=name, role=role, experience_years=float(exp) if exp else None,
                      locations=locations, skills=skills, exclude_keywords=exclude)
    PROFILES_DIR.mkdir(exist_ok=True)
    path = PROFILES_DIR / f"{slug(name)}.toml"
    if path.exists() and ask(f"{path.name} exists. Overwrite? (y/n)", "n").lower() != "y":
        sys.exit("Nothing written.")
    path.write_text(to_toml(profile))
    print(f"\nSaved {path}\nLinkedIn queries: {profile.linkedin_search()}\nNaukri queries:   {profile.naukri_search()}")
    print(f"Run it with:  harvest run -p {path.stem}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="harvest", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=ROOT / "config.toml")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("ui", help="open the setup screen (the default when no command is given)")
    sub.add_parser("init", help="create a search profile interactively")
    sub.add_parser("profiles", help="list search profiles")
    sub.add_parser("login", help="sign in to LinkedIn once, by hand")

    r = sub.add_parser("run", help="search the portals")
    r.add_argument("-p", "--profile", help="profile name from profiles/ (default: the last one used)")
    r.add_argument("--sources", default="naukri,linkedin", help="comma list: naukri,linkedin")
    r.add_argument("--limit", type=int, help="posts per search (overrides the saved value)")
    r.add_argument("--headless", action="store_true", help="hide the browser window (Naukri refuses headless)")

    s = sub.add_parser("scan", help="extract from a text file ('-' for stdin)")
    s.add_argument("file")
    s.add_argument("-p", "--profile")

    e = sub.add_parser("export", help="print addresses first seen recently")
    e.add_argument("--days", type=float, default=1)
    e.add_argument("-p", "--profile")

    args = ap.parse_args(argv)

    if args.cmd in (None, "ui"):
        from .ui import run_screen
        return asyncio.run(run_screen(args.config))
    if args.cmd == "init":
        return init()
    if args.cmd == "login":
        return asyncio.run(login())
    if args.cmd == "profiles":
        for path in sorted(PROFILES_DIR.glob("*.toml")):
            p = Profile.load(path)
            exp = f"{p.experience_years:g} yrs" if p.experience_years is not None else "any exp"
            print(f"{path.stem:22} {p.role:22} {exp:9} {', '.join(p.locations) or 'any city'}")
        return

    setup = load(args.config, args.profile)
    store = Store(setup.data_dir / "leads.db")
    if args.cmd == "run":
        args.sources = {s.strip() for s in args.sources.split(",")}
        report(asyncio.run(run(args, setup, store)), setup.out_dir)
    elif args.cmd == "scan":
        text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text()
        leads = leads_from(Post(source="paste", url="", author="", text=text), setup)
        report([(l, store.record(l)) for l in leads], setup.out_dir)
    elif args.cmd == "export":
        print("\n".join(store.kept_since(args.days)))


if __name__ == "__main__":
    main()
