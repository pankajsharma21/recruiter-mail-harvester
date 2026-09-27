import asyncio

from playwright.async_api import TimeoutError as PlaywrightTimeout

from conftest import example
from harvester import cli
from harvester.sources import Post
from harvester.store import Store

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
