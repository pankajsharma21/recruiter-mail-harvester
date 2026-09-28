"""LinkedIn: content search for recent hiring posts (last 24 hours, week or month).

Needs a logged-in session: run `harvest login` once and sign in by hand. The
password is never seen by this tool; only the browser profile keeps the cookie.

Recruiters post "we're hiring, share your CV at x@y.com" far more often than they put
an address in a formal job listing, so posts (not the Jobs tab) are the source.
"""

from collections.abc import AsyncIterator
from urllib.parse import quote

from playwright.async_api import Page

from . import Blocked, Post, polite_pause

SEARCH_URL = ("https://www.linkedin.com/search/results/content/"
              "?keywords={q}&datePosted=%22{within}%22&sortBy=%22date_posted%22")
POST = "[role=listitem]"


async def _expand_all(page: Page) -> None:
    # Long posts are truncated behind a "…more" button, and the address is usually
    # in the truncated part.
    await page.evaluate("""() => {
        for (const b of document.querySelectorAll('button')) {
            const t = b.innerText.trim().toLowerCase();
            if (t === '…more' || t === '...more' || t === 'see more') b.click();
        }
    }""")


async def _load_more(page: Page, rounds: int) -> None:
    # Lazy loading only reacts to real wheel events; window.scrollTo() does nothing.
    # viewport_size is None when the window sets the size (no_viewport), so ask the page.
    box = page.viewport_size or await page.evaluate("({width: innerWidth, height: innerHeight})")
    await page.mouse.move(box["width"] / 2, box["height"] / 2)
    for _ in range(rounds):
        await page.mouse.wheel(0, 2500)
        await page.wait_for_timeout(1500)


def search_url(query: str, within: str = "past-24h") -> str:
    return SEARCH_URL.format(q=quote(query), within=within)


async def posts(page: Page, query: str, limit: int, within: str = "past-24h") -> AsyncIterator[Post]:
    await page.goto(search_url(query, within), wait_until="domcontentloaded")
    await page.wait_for_timeout(5000)
    if "/login" in page.url or "/authwall" in page.url or "/checkpoint" in page.url:
        raise Blocked("LinkedIn session missing or expired - run `harvest login`")

    # One wheel round loads roughly three posts; scroll enough to reach the limit.
    await _load_more(page, min(60, max(8, limit // 3 + 2)))
    await _expand_all(page)
    await page.wait_for_timeout(1000)

    items = await page.evaluate("""(sel) => {
        // Only outermost list items: comments and reshares nest their own.
        const all = [...document.querySelectorAll(sel)];
        return all.filter(el => !el.parentElement.closest(sel)).map(el => {
            // Search results carry no post permalink in the DOM, so a post falls back
            // to the search URL. The avatar link comes first and has no text, so the
            // author is the first profile/company link that does.
            const link = el.querySelector('a[href*="/feed/update/"], a[href*="/posts/"]');
            const actor = [...el.querySelectorAll('a[href*="/in/"], a[href*="/company/"]')]
                .map(a => a.innerText.trim().split('\\n')[0]).find(t => t);
            return {
                text: el.innerText,
                url: link ? link.href.split('?')[0] : location.href,
                author: actor || '',
            };
        });
    }""", POST)

    for item in items[:limit]:
        yield Post(source="linkedin", url=item["url"], author=item["author"], text=item["text"])
    await polite_pause()
