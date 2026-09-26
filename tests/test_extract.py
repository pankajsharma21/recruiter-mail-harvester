from harvester.extract import find_emails, snippet


def test_plain_and_obfuscated():
    text = "Share CV at Jobs@Acme.in or hr [at] acme [dot] co [dot] in."
    assert find_emails(text) == ["jobs@acme.in", "hr@acme.co.in"]


def test_bare_at_is_not_rewritten():
    assert find_emails("Hiring at Gurugram, dot net not needed") == []


def test_drops_images_and_noreply():
    text = "logo@2x.png noreply@naukri.com do-not-reply@x.com real.person@corp.com"
    assert find_emails(text) == ["real.person@corp.com"]


def test_dedup_and_trailing_dot():
    assert find_emails("a@b.com. again A@B.COM") == ["a@b.com"]


def test_snippet_shows_context():
    s = snippet("x " * 100 + "mail me at a@b.com please", "a@b.com")
    assert "a@b.com" in s and s.startswith("…")
