"""Decide whether a post/JD is a hiring post worth mailing, and say why if not."""

import re
from dataclasses import dataclass, field


def words_rx(words: list[str], whole: bool = False) -> str:
    """Regex matching any of `words` at a word start (and, with whole=True, a word end).

    \\b only works next to a letter or digit: "\\b.net" never matched " .NET" after a
    space. So the boundary is added only on a side that starts/ends with a letter or
    digit; a symbol such as the "." of ".net" or the "+" of "c++" is its own edge, and
    ".net" still matches inside "ASP.NET".
    """
    def one(w: str) -> str:
        rx = re.escape(w)
        if w[:1].isalnum() or w[:1] == "_":
            rx = r"(?<!\w)" + rx
        if whole and (w[-1:].isalnum() or w[-1:] == "_"):
            rx += r"(?!\w)"
        return rx
    return "(?:" + "|".join(one(w) for w in words if w) + ")"


@dataclass
class Rules:
    # At least one of these must appear, or the post is off-topic.
    role_keywords: list[str] = field(default_factory=list)
    # label -> regex. The first match drops the post and its label becomes the reason.
    drop_patterns: dict[str, str] = field(default_factory=dict)
    # Exact addresses and whole domains that are never worth mailing.
    blocked_emails: list[str] = field(default_factory=list)
    blocked_domains: list[str] = field(default_factory=list)
    # Posts matching this are job posts; labels in soft_drops never drop them.
    hiring_phrase: str = ""
    soft_drops: list[str] = field(default_factory=list)

    def __post_init__(self):
        # Leading word boundary only: "qa" must not match "Qatar", but "microservice"
        # should still match "microservices".
        self._role = (re.compile(words_rx(self.role_keywords), re.I)
                      if self.role_keywords else None)
        self._drops = [(label, re.compile(rx, re.I)) for label, rx in self.drop_patterns.items()]
        self._emails = {e.lower() for e in self.blocked_emails}
        self._domains = {d.lower().lstrip("@") for d in self.blocked_domains}
        self._hiring = re.compile(self.hiring_phrase, re.I) if self.hiring_phrase else None

    @classmethod
    def from_dict(cls, d: dict) -> "Rules":
        return cls(
            role_keywords=d.get("role_keywords", []),
            drop_patterns=d.get("drop_patterns", {}),
            blocked_emails=d.get("blocked_emails", []),
            blocked_domains=d.get("blocked_domains", []),
            hiring_phrase=d.get("hiring_phrase", ""),
            soft_drops=d.get("soft_drops", []),
        )

    def check_post(self, text: str) -> str | None:
        """None if the post is kept, otherwise the reason it was dropped."""
        is_job_post = bool(self._hiring and self._hiring.search(text))
        for label, rx in self._drops:
            if label in self.soft_drops and is_job_post:
                continue
            if m := rx.search(text):
                # Keep the matched words: a rule that misfires is obvious in the CSV.
                return f'{label}: "{" ".join(m.group(0).split())}"'
        if self._role and not self._role.search(text):
            return "no matching role"
        return None

    def check_email(self, email: str) -> str | None:
        if email in self._emails:
            return "blocked address"
        if email.split("@", 1)[1] in self._domains:
            return "blocked domain"
        return None
