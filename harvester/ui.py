"""The setup screen: pick a saved person or fill in a new one, then search.

It is an HTML page shown in the same Chrome window the tool already drives, so it
needs no extra GUI toolkit and looks the same on Linux, Windows and macOS. The page
calls into Python through Playwright's exposed functions, and Python pushes progress
back with page.evaluate().
"""

import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from .browser import browser
from .profile import Profile, slug, to_toml
from .store import Store

HTML = Path(__file__).with_name("ui.html")


def _people(profiles_dir: Path) -> list[dict]:
    people = []
    for path in sorted(profiles_dir.glob("*.toml")):
        try:
            people.append({"id": path.stem, **asdict(Profile.load(path))})
        except Exception:
            continue  # a hand-edited file with a typo should not break the screen
    return people


def _new_id(profiles_dir: Path, name: str) -> str:
    base = slug(name)
    pid, n = base, 2
    while (profiles_dir / f"{pid}.toml").exists():
        pid, n = f"{base}-{n}", n + 1
    return pid


def _short(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _profile_from(data: dict) -> Profile:
    fields = Profile.__dataclass_fields__
    return Profile(**{k: v for k, v in data.items() if k in fields})


async def run_screen(config_path: Path) -> None:
    # Imported here to avoid a cycle: cli imports this module for its default command.
    from . import cli

    cfg = cli.load_config(config_path)
    profiles_dir = cli.PROFILES_DIR
    profiles_dir.mkdir(exist_ok=True)
    last_file = profiles_dir / ".last"
    closed = asyncio.Event()

    async with browser(headless=False) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        page.on("close", lambda _: closed.set())

        async def log(line: str) -> None:
            print(line)
            if not page.is_closed():
                await page.evaluate("l => window.ui.log(l)", line)

        async def search(profile_id: str, profile: Profile) -> None:
            setup = cli.make_setup(cfg, profile_id, profile)
            store = Store(setup.data_dir / "leads.db")
            blocked: list[str] = []

            async def log_and_note(line: str) -> None:
                if line.startswith("  ! "):
                    blocked.append(line[4:])
                await log(line)

            await log("Searching for " + cli.describe(profile))
            try:
                work = await ctx.new_page()
                try:
                    found = await cli.harvest_within(
                        work, setup, store, set(profile.sources), profile.posts_per_search,
                        log_and_note, timeout=(profile.timeout_minutes * 60) or None)
                finally:
                    if not work.is_closed():
                        await work.close()
                new_emails = cli.save_outputs(found, setup.out_dir)
                rows = [{"email": l.email, "kept": l.kept, "author": l.author, "source": l.source,
                         "tag": ("new" if new else "already seen") if l.kept else l.status}
                        for l, new in found]
                rows.sort(key=lambda r: (not r["kept"], r["tag"] != "new"))
                if not page.is_closed():
                    await page.bring_to_front()
                    await page.evaluate("r => window.ui.done(r)", {
                        "found": len(found), "kept": sum(l.kept for l, _ in found),
                        "new_emails": new_emails, "rows": rows, "blocked": blocked,
                        "saved_to": _short(setup.out_dir / "new_emails.txt"),
                    })
            except Exception as e:
                # A scrape can fail many ways (login wall, changed page, closed tab).
                # Report it on the screen instead of leaving the button stuck.
                print(f"  ! Search stopped: {e}")
                if not page.is_closed():
                    await page.bring_to_front()
                    await page.evaluate("m => window.ui.fail(m)", f"Search stopped: {e}")

        async def harvest_run(data: dict) -> dict:
            profile = _profile_from(data)
            profile_id = data.get("id") or _new_id(profiles_dir, profile.name)
            (profiles_dir / f"{profile_id}.toml").write_text(to_toml(profile))
            last_file.write_text(profile_id)
            # Answer the page first so it can show the saved person, then search.
            asyncio.create_task(search(profile_id, profile))
            return {"id": profile_id, "people": _people(profiles_dir)}

        async def harvest_status() -> bool:
            return await cli.signed_in(ctx)

        async def harvest_login() -> bool:
            if await cli.signed_in(ctx):
                return True  # already signed in: don't flash a tab that closes by itself
            tab = await ctx.new_page()
            ok = await cli.sign_in(tab)
            if not tab.is_closed():
                await tab.close()
            await page.bring_to_front()
            return ok

        await page.expose_function("harvestRun", harvest_run)
        await page.expose_function("harvestLogin", harvest_login)
        await page.expose_function("harvestStatus", harvest_status)

        last = last_file.read_text().strip() if last_file.exists() else None
        boot = (f"<script>window.__PEOPLE__={json.dumps(_people(profiles_dir))};"
                f"window.__LAST__={json.dumps(last)};</script>")
        await page.set_content(HTML.read_text().replace("<script>", boot + "\n<script>", 1))
        print("The setup screen is open in Chrome. Close the window to quit.")
        await closed.wait()
