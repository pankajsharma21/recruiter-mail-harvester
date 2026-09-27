"""SQLite history of every address ever harvested, so a run only reports what is new."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    email       TEXT PRIMARY KEY,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    source      TEXT NOT NULL,
    url         TEXT,
    author      TEXT,
    snippet     TEXT,
    status      TEXT NOT NULL,   -- 'kept' or the drop reason
    times_seen  INTEGER NOT NULL DEFAULT 1
);
"""


@dataclass
class Lead:
    email: str
    source: str
    url: str
    author: str
    snippet: str
    status: str = "kept"

    @property
    def kept(self) -> bool:
        return self.status == "kept"


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def record(self, lead: Lead) -> bool:
        """Save the lead. True if it is new: never seen, or only ever seen dropped.

        The same recruiter often shows up in an off-target post first and a
        matching one later; the later match must not be lost as "seen before".
        """
        now = datetime.now().isoformat(timespec="seconds")
        row = self.db.execute("SELECT status FROM leads WHERE email=?", (lead.email,)).fetchone()
        if row:
            promote = lead.kept and row[0] != "kept"
            if promote:
                self.db.execute(
                    "UPDATE leads SET status='kept', first_seen=?, source=?, url=?, author=?, snippet=? "
                    "WHERE email=?", (now, lead.source, lead.url, lead.author, lead.snippet, lead.email))
            self.db.execute(
                "UPDATE leads SET last_seen=?, times_seen=times_seen+1 WHERE email=?", (now, lead.email))
            self.db.commit()
            return promote
        self.db.execute(
            "INSERT INTO leads VALUES (?,?,?,?,?,?,?,?,1)",
            (lead.email, now, now, lead.source, lead.url, lead.author, lead.snippet, lead.status))
        self.db.commit()
        return True

    def kept_since(self, days: float) -> list[str]:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        rows = self.db.execute(
            "SELECT email FROM leads WHERE status='kept' AND first_seen>=? ORDER BY first_seen", (cutoff,))
        return [r[0] for r in rows]

    def stats(self) -> dict[str, int]:
        rows = self.db.execute("SELECT source, COUNT(*) FROM leads WHERE status='kept' GROUP BY source")
        return dict(rows)
