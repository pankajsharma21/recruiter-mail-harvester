import asyncio

from harvester import cli


class FakeContext:
    def __init__(self, page):
        self.page = page

    async def cookies(self, url):
        return self.page.cookie_jar


class FakePage:
    """Walks through a scripted list of (url, cookies) states, one per poll."""

    def __init__(self, states):
        self.states = list(states)
        self.url = "about:blank"
        self.cookie_jar = []
        self.context = FakeContext(self)

    async def goto(self, url):
        self.url = url

    def is_closed(self):
        return False

    def step(self):
        if self.states:
            self.url, self.cookie_jar = self.states.pop(0)


def run_sign_in(page):
    async def fast_sleep(_):
        page.step()

    real_sleep = asyncio.sleep
    asyncio.sleep = fast_sleep
    try:
        return asyncio.run(cli.sign_in(page, minutes=1))
    finally:
        asyncio.sleep = real_sleep


def test_leaving_the_login_page_without_signing_in_is_not_success():
    # "Join now" or a consent page moves off /login but sets no session cookie.
    page = FakePage([("https://www.linkedin.com/signup/cold-join", [])] * 60)
    assert run_sign_in(page) is False


def test_session_cookie_means_signed_in():
    page = FakePage([
        ("https://www.linkedin.com/login", []),
        ("https://www.linkedin.com/checkpoint/lg/login-submit", []),
        ("https://www.linkedin.com/feed/", [{"name": "li_at", "value": "abc"}]),
    ])
    assert run_sign_in(page) is True


def test_already_signed_in_opens_nothing():
    # A session saved on an earlier run: no login page, no tab flashing open and shut.
    page = FakePage([])
    page.cookie_jar = [{"name": "li_at", "value": "abc"}]
    assert run_sign_in(page) is True
    assert page.url == "about:blank"
