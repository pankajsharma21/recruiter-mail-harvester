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

from playwright.async_api import Error as PlaywrightError

from . import extract
from .browser import browser
from .filters import Rules, words_rx
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
        drops["excluded keyword"] = words_rx(profile.exclude_keywords, whole=True)
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
    return (f"{p.name} · {', '.join(p.all_roles())}"
            + (f" · {p.experience_years:g} yrs" if p.experience_years is not None else "")
            + (f" · {', '.join(p.locations)}" if p.locations else " · any city")
            + f" · {POSTED_WITHIN[p.posted_within]['label']}")


async def harvest(page, setup: Setup, store: Store, sources: set[str], limit: int,
                  log=print, out: list | None = None) -> list[tuple[Lead, bool]]:
    """Search every chosen source with the profile's queries. `log` receives progress lines.
    Appends to `out` if given, so a caller that cancels this on a timeout still keeps
    everything found before the cutoff."""
    found: list[tuple[Lead, bool]] = out if out is not None else []
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
            except PlaywrightError as e:
                # A page that never loads (LinkedIn slows down after several searches)
                # used to end the whole run, and the addresses already found were never
                # written out even though the store had marked them as seen.
                first = str(e).splitlines()[0][:120]
                await _maybe_await(log(f"  ! {name} search did not load, skipped: {first}"))
    return found


async def harvest_within(page, setup: Setup, store: Store, sources: set[str], limit: int,
                         log=print, timeout: float | None = None,
                         stop: asyncio.Event | None = None) -> list[tuple[Lead, bool]]:
    """Run harvest, but end early after `timeout` seconds (None or 0 = no limit) or when
    `stop` is set (the screen's Stop button), and return whatever was found by then."""
    found: list[tuple[Lead, bool]] = []
    job = asyncio.ensure_future(harvest(page, setup, store, sources, limit, log, out=found))
    stopper = asyncio.ensure_future(stop.wait()) if stop else None
    waiting = {job, stopper} - {None}
    try:
        done, _ = await asyncio.wait(waiting, timeout=timeout or None,
                                     return_when=asyncio.FIRST_COMPLETED)
    finally:
        if stopper:
            stopper.cancel()
    if job in done:
        return job.result()  # finished on its own (re-raises if it failed)
    job.cancel()
    try:
        await job
    except asyncio.CancelledError:
        pass
    why = "Stopped" if stop and stop.is_set() else "Time limit reached"
    kept = sum(l.kept for l, _ in found)
    await _maybe_await(log(f"  · {why} - returning {kept} matched of {len(found)} found so far."))
    return found


async def _maybe_await(x):
    if asyncio.iscoroutine(x):
        await x


async def run(args, setup: Setup, store: Store) -> list[tuple[Lead, bool]]:
    print("Profile:", describe(setup.profile))
    async with browser(headless=args.headless) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        minutes = args.timeout if args.timeout is not None else setup.profile.timeout_minutes
        return await harvest_within(page, setup, store, args.sources,
                                    args.limit or setup.profile.posts_per_search,
                                    timeout=(minutes * 60) or None)


async def signed_in(ctx) -> bool:
    """True when the tool's Chrome profile already holds a LinkedIn session."""
    cookies = await ctx.cookies("https://www.linkedin.com")
    return any(c["name"] == "li_at" and c["value"] for c in cookies)


async def sign_in(page, minutes: int = 10) -> bool:
    """Open LinkedIn's login page and wait until the person has signed in by hand.

    Waiting for the window to be closed let people close it one step too early,
    before the session cookie existed. Watching the URL closed the tab too early
    the other way: "Join now", a signup or consent page, or any other LinkedIn page
    that is not /login looked like success. Poll for the `li_at` session cookie,
    which LinkedIn sets only once someone is actually signed in.
    """
    if await signed_in(page.context):
        return True  # the session saved last time is still there; nothing to do
    await page.goto("https://www.linkedin.com/login")
    for _ in range(minutes * 60):
        await asyncio.sleep(1)
        if page.is_closed():
            return False
        if await signed_in(page.context):
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
    r.add_argument("--sources", help="comma list: naukri,linkedin (default: the person's saved choice)")
    r.add_argument("--timeout", type=float, help="stop after N minutes and return what was found (0 = no limit)")
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
            try:
                p = Profile.load(path)
            except Exception as e:  # one hand-edited typo should not hide everyone else
                print(f"{path.stem:22} (cannot read: {e})")
                continue
            exp = f"{p.experience_years:g} yrs" if p.experience_years is not None else "any exp"
            print(f"{path.stem:22} {', '.join(p.all_roles()):22} {exp:9} {', '.join(p.locations) or 'any city'}")
        return

    setup = load(args.config, args.profile)
    store = Store(setup.data_dir / "leads.db")
    if args.cmd == "run":
        args.sources = ({s.strip() for s in args.sources.split(",") if s.strip()} if args.sources
                        else set(setup.profile.sources))
        report(asyncio.run(run(args, setup, store)), setup.out_dir)
    elif args.cmd == "scan":
        text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text()
        leads = leads_from(Post(source="paste", url="", author="", text=text), setup)
        report([(l, store.record(l)) for l in leads], setup.out_dir)
    elif args.cmd == "export":
        print("\n".join(store.kept_since(args.days)))


if __name__ == "__main__":
    main()
