"""Naukri: search results -> open each job -> read the description.

Search pages need no login. Most JDs hide the recruiter's address, but a fair share
say "share your resume at ...", and those are the ones worth collecting.
"""

import re
from collections.abc import AsyncIterator
from urllib.parse import quote

from playwright.async_api import Page

from . import Blocked, Post, polite_pause

SEARCH_URL = "https://www.naukri.com/{slug}-jobs{page}?jobAge={age}"
PAGE_SIZE = 20  # Naukri lists 20 jobs per results page
JOB_LINK = "a.title"
JD_BODY = "[class*=job-desc-container]"
COMPANY = "[class*=comp-name] a, [class*=comp-name]"


def search_url(query: str, days: int, page: int = 1) -> str:
    slug = quote(re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-"))
    return SEARCH_URL.format(slug=slug, age=days, page=f"-{page}" if page > 1 else "")


async def _job_links(page: Page, query: str, days: int, limit: int) -> list[str]:
    """Links from as many results pages as the limit needs (page 2 is /<slug>-jobs-2)."""
    links: list[str] = []
    for n in range(1, (limit - 1) // PAGE_SIZE + 2):
        if n > 1:
            await polite_pause()
        await page.goto(search_url(query, days, n), wait_until="domcontentloaded")
        try:
            await page.wait_for_selector(JOB_LINK, timeout=20_000)
        except Exception:
            # Naukri's CDN answers headless Chrome with a bare "Access Denied" page.
            if "Access Denied" in await page.title():
                raise Blocked("Naukri blocked this browser (Access Denied) - run without --headless")
            break  # no (more) results
        found = await page.eval_on_selector_all(JOB_LINK, "els => els.map(a => a.href)")
        links += [u for u in found if u not in links]
        if len(links) >= limit or len(found) < PAGE_SIZE:
            break
    return links[:limit]


async def posts(page: Page, query: str, limit: int, days: int = 1) -> AsyncIterator[Post]:
    links = await _job_links(page, query, days, limit)

    for url in links:
        await polite_pause()
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_selector(JD_BODY, timeout=15_000)
        except Exception:
            continue  # expired or removed listing
        text = await page.inner_text(JD_BODY)
        company = await page.locator(COMPANY).first.inner_text() if await page.locator(COMPANY).count() else ""
        title = await page.locator("h1").first.inner_text() if await page.locator("h1").count() else ""
        yield Post(source="naukri", url=url, author=company.strip().split("\n")[0], text=f"{title}\n{text}")
