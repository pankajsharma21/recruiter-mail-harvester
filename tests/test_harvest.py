import asyncio

from playwright.async_api import TimeoutError as PlaywrightTimeout

from conftest import example
from harvester import cli
from harvester.sources import Post
from harvester.store import Lead, Store

JAVA = example("java-developer")


class FlakySource:
    """First search never loads, like LinkedIn after a few searches; later ones work."""

    def __init__(self):
        self.calls = 0

    async def posts(self, page, query, limit, **extra):
        self.calls += 1
        if self.calls == 1:
            raise PlaywrightTimeout("Page.goto: Timeout 30000ms exceeded.")
        yield Post("linkedin", "https://example.test/post", "Recruiter",
                   "Hiring Java developer, Spring Boot, 5 yrs. Share CV at jobs@acme.example")


def test_a_search_that_times_out_is_skipped_not_fatal(tmp_path, monkeypatch):
    source = FlakySource()
    monkeypatch.setattr(cli, "linkedin", source)
    lines = []
    found = asyncio.run(cli.harvest(None, JAVA, Store(tmp_path / "leads.db"), {"linkedin"},
                                    5, lines.append))
    assert source.calls >= 2
    assert any("did not load, skipped" in line for line in lines)
    assert [lead.email for lead, _ in found] == ["jobs@acme.example"]


def lead(email, status="kept"):
    return Lead(email=email, source="s", url="", author="", snippet="", status=status)


def test_harvest_within_returns_partial_on_timeout(monkeypatch):
    async def slow(page, setup, store, sources, limit, log=print, out=None):
        out.append((lead("a@x.com"), True))
        await asyncio.sleep(5)                       # would run past the tiny timeout
        out.append((lead("b@y.com"), True))          # never reached
        return out

    monkeypatch.setattr(cli, "harvest", slow)
    logs = []
    async def log(m): logs.append(m)

    res = asyncio.run(cli.harvest_within(None, None, None, {"linkedin"}, 1, log=log, timeout=0.2))
    assert [l.email for l, _ in res] == ["a@x.com"]          # only found before the cutoff
    assert any("Time limit reached" in m for m in logs)


def test_harvest_within_no_timeout_runs_fully(monkeypatch):
    async def quick(page, setup, store, sources, limit, log=print, out=None):
        out.extend([(lead("a@x.com"), True), (lead("b@y.com"), True)])
        return out

    monkeypatch.setattr(cli, "harvest", quick)
    res = asyncio.run(cli.harvest_within(None, None, None, {"linkedin"}, 1, timeout=None))
    assert [l.email for l, _ in res] == ["a@x.com", "b@y.com"]
