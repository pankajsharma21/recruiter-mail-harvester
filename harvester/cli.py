"""harvest - collect recruiter email addresses from job portals.

    harvest login              open the browser once and sign in to LinkedIn by hand
    harvest run                search every source, print and save what is new
    harvest scan FILE          extract from pasted text (no browser)
    harvest export --days 1    addresses first seen in the last N days, one per line
"""

import argparse
import asyncio
import csv
import sys
import tomllib
from datetime import date
from pathlib import Path

from . import extract
from .browser import browser
from .filters import Rules
from .sources import Blocked, Post, linkedin, naukri
from .store import Lead, Store

ROOT = Path.cwd()
DB_PATH = ROOT / "data" / "leads.db"
OUT_DIR = ROOT / "output"


def load_config(path: Path) -> tuple[dict, Rules]:
    cfg = tomllib.loads(path.read_text())
    rules = cfg.get("rules", {})
    return cfg.get("search", {}), Rules.from_dict({**rules, **rules.get("lists", {})})


def leads_from(post: Post, rules: Rules) -> list[Lead]:
    emails = extract.find_emails(post.text)
    if not emails:
        return []
    post_reason = rules.check_post(post.text)
    return [
        Lead(email=e, source=post.source, url=post.url, author=post.author,
             snippet=extract.snippet(post.text, e),
             status=post_reason or rules.check_email(e) or "kept")
        for e in emails
    ]


def report(leads: list[tuple[Lead, bool]], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "leads.csv", "a", newline="") as f:
        w = csv.writer(f)
        if f.tell() == 0:
            w.writerow(["email", "new", "status", "source", "author", "url", "snippet"])
        for lead, new in leads:
            w.writerow([lead.email, new, lead.status, lead.source, lead.author, lead.url, lead.snippet])

    new_kept = [l.email for l, new in leads if new and l.kept]
    with open(out / "new_emails.txt", "a") as f:
        f.writelines(e + "\n" for e in new_kept)

    print(f"\n{'EMAIL':38} {'STATUS':18} {'SOURCE':9} AUTHOR")
    for lead, new in leads:
        tag = lead.status if lead.kept is False else ("NEW" if new else "seen before")
        print(f"{lead.email:38} {tag:18} {lead.source:9} {lead.author[:30]}")
    kept = sum(l.kept for l, _ in leads)
    print(f"\n{len(leads)} found · {kept} kept · {len(new_kept)} new → {out / 'new_emails.txt'}")


async def run(args, search: dict, rules: Rules, store: Store) -> list[tuple[Lead, bool]]:
    found: list[tuple[Lead, bool]] = []
    limit = args.limit or search.get("limit", 25)

    def take(post: Post):
        for lead in leads_from(post, rules):
            found.append((lead, store.record(lead)))
            print(f"  + {lead.email}  ({lead.status})")

    async with browser(headless=args.headless) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        plan = [
            ("naukri", naukri, search.get("naukri_queries", []), {"days": search.get("naukri_days", 1)}),
            ("linkedin", linkedin, search.get("linkedin_queries", []), {}),
        ]
        for name, source, queries, extra in plan:
            if name not in args.sources:
                continue
            for q in queries:
                print(f"[{name}] {q}")
                try:
                    async for post in source.posts(page, q, limit, **extra):
                        take(post)
                except Blocked as e:
                    # One refusal means the rest of this portal's queries will fail too.
                    print(f"  ! {e}", file=sys.stderr)
                    break
    return found


async def login() -> None:
    async with browser(headless=False) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://www.linkedin.com/login")
        print("Sign in inside the browser window, then close it. The session is kept for later runs.")
        await page.wait_for_event("close", timeout=0)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="harvest", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=ROOT / "config.toml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login", help="sign in to LinkedIn once, by hand")

    r = sub.add_parser("run", help="search the portals")
    r.add_argument("--sources", default="naukri,linkedin", help="comma list: naukri,linkedin")
    r.add_argument("--limit", type=int, help="posts per query (overrides config)")
    r.add_argument("--headless", action="store_true", help="hide the browser window (Naukri refuses headless)")

    s = sub.add_parser("scan", help="extract from a text file ('-' for stdin)")
    s.add_argument("file")

    e = sub.add_parser("export", help="print addresses first seen recently")
    e.add_argument("--days", type=float, default=1)

    args = ap.parse_args(argv)
    search, rules = load_config(args.config)
    store = Store(DB_PATH)
    out = OUT_DIR / date.today().isoformat()

    if args.cmd == "login":
        asyncio.run(login())
    elif args.cmd == "run":
        args.sources = {s.strip() for s in args.sources.split(",")}
        report(asyncio.run(run(args, search, rules, store)), out)
    elif args.cmd == "scan":
        text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text()
        leads = leads_from(Post(source="paste", url="", author="", text=text), rules)
        report([(l, store.record(l)) for l in leads], out)
    elif args.cmd == "export":
        print("\n".join(store.kept_since(args.days)))


if __name__ == "__main__":
    main()
