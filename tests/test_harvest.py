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


def test_stop_button_ends_the_search_and_keeps_what_was_found(monkeypatch):
    async def slow(page, setup, store, sources, limit, log=print, out=None):
        out.append((lead("a@x.com"), True))
        await asyncio.sleep(5)
        out.append((lead("b@y.com"), True))
        return out

    monkeypatch.setattr(cli, "harvest", slow)
    logs = []

    async def main():
        stop = asyncio.Event()
        asyncio.get_running_loop().call_later(0.2, stop.set)  # the person presses Stop
        return await cli.harvest_within(None, None, None, {"linkedin"}, 1, log=logs.append,
                                        timeout=None, stop=stop)

    res = asyncio.run(main())
    assert [l.email for l, _ in res] == ["a@x.com"]
    assert any(m.startswith("  · Stopped") for m in logs)


def test_a_failing_search_still_raises(monkeypatch):
    async def broken(page, setup, store, sources, limit, log=print, out=None):
        raise RuntimeError("page changed")

    monkeypatch.setattr(cli, "harvest", broken)
    try:
        asyncio.run(cli.harvest_within(None, None, None, {"linkedin"}, 1, timeout=10,
                                       stop=asyncio.Event()))
    except RuntimeError as e:
        assert "page changed" in str(e)
    else:
        raise AssertionError("the error was swallowed")


def test_run_uses_the_persons_saved_sources(tmp_path, monkeypatch):
    # `harvest run -p NAME` searched both portals even for a Naukri-only person.
    import shutil
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "PROFILES_DIR", tmp_path / "profiles")
    (tmp_path / "profiles").mkdir()
    from harvester.profile import Profile, to_toml
    (tmp_path / "profiles" / "n.toml").write_text(to_toml(Profile(name="n", role="Accountant", sources=["naukri"])))
    shutil.copy(cli.Path(__file__).parents[1] / "config.toml", tmp_path / "config.toml")
    seen = {}

    async def fake_run(args, setup, store):
        seen["sources"] = args.sources
        return []

    monkeypatch.setattr(cli, "run", fake_run)
    cli.main(["--config", str(tmp_path / "config.toml"), "run", "-p", "n"])
    assert seen["sources"] == {"naukri"}
    cli.main(["--config", str(tmp_path / "config.toml"), "run", "-p", "n", "--sources", "linkedin"])
    assert seen["sources"] == {"linkedin"}


def test_excluded_words_with_symbols_still_drop(tmp_path):
    from harvester.profile import Profile
    setup = cli.make_setup({}, "x", Profile(name="x", role="Developer", exclude_keywords=[".net", "c++"]))
    assert setup.rules.check_post("Developer needed, .NET stack") is not None
    assert setup.rules.check_post("Developer needed, C++ stack") is not None
    assert setup.rules.check_post("Developer needed, Python stack") is None
