"""Each source turns a search query into a stream of Posts (a JD, a hiring post, ...)."""

import asyncio
import random
from dataclasses import dataclass


@dataclass
class Post:
    source: str
    url: str
    author: str
    text: str


class Blocked(RuntimeError):
    """The portal refused the session: bot wall, login wall, or rate limit."""


async def polite_pause(low: float = 2.0, high: float = 5.0) -> None:
    """A human-ish gap between page loads. Portals rate-limit and flag bursts."""
    await asyncio.sleep(random.uniform(low, high))
