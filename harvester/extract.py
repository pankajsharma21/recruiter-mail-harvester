"""Pull email addresses out of free text: job descriptions, hiring posts, pasted lists."""

import re

# Recruiters dodge scrapers with "name [at] company [dot] com". Only the bracketed
# forms are rewritten: a bare " at " would turn "hiring at Gurugram" into garbage.
_OBFUSCATIONS = [
    (re.compile(r"\s*[\[\(\{<]\s*at\s*[\]\)\}>]\s*", re.I), "@"),
    (re.compile(r"\s*[\[\(\{<]\s*dot\s*[\]\)\}>]\s*", re.I), "."),
]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")

# Things that match the regex but are not mailboxes: retina image names, asset hashes.
_NOT_A_MAILBOX = re.compile(r"\.(png|jpe?g|gif|svg|webp|css|js)$|@\d+x\.", re.I)

# Addresses that exist but never reach a person.
_NO_REPLY = re.compile(r"^(no-?reply|do-?not-?reply|donotreply|notifications?|mailer-daemon|postmaster)@", re.I)


def deobfuscate(text: str) -> str:
    for pattern, repl in _OBFUSCATIONS:
        text = pattern.sub(repl, text)
    return text


def find_emails(text: str) -> list[str]:
    """Unique, lower-cased addresses in the order they first appear."""
    seen: dict[str, None] = {}
    for raw in EMAIL_RE.findall(deobfuscate(text)):
        email = raw.strip(".").lower()
        if _NOT_A_MAILBOX.search(email) or _NO_REPLY.match(email):
            continue
        seen.setdefault(email, None)
    return list(seen)


def snippet(text: str, email: str, width: int = 90) -> str:
    """A short window of text around the address, for eyeballing why it was kept."""
    flat = " ".join(deobfuscate(text).split())
    i = flat.lower().find(email)
    if i < 0:
        return flat[:width * 2]
    start = max(0, i - width)
    return ("…" if start else "") + flat[start:i + len(email) + width // 3]
