"""One persistent Chrome profile, kept outside the repo, so logins survive between runs."""

from contextlib import asynccontextmanager
from pathlib import Path

from playwright.async_api import async_playwright

PROFILE_DIR = Path.home() / ".local/share/recruiter-mail-harvester/profile"


@asynccontextmanager
async def browser(headless: bool = False):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        # channel="chrome" uses the installed Google Chrome, so no browser download,
        # and sites see a normal Chrome rather than a test build.
        ctx = await p.chromium.launch_persistent_context(
            PROFILE_DIR,
            channel="chrome",
            headless=headless,
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            yield ctx
        finally:
            await ctx.close()
