"""Polite, cached HTTP fetching.

Raw downloads are cached under data/raw so the whole pipeline is reproducible
offline and we never hammer a public statistical agency.
"""
from __future__ import annotations

import time
from pathlib import Path

import requests

from .config import RAW

# BLS asks scrapers to identify themselves with a contact address.
USER_AGENT = "rate-shock academic event study (garywangsmes@gmail.com)"
_SESSION: requests.Session | None = None


def session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT})
        _SESSION = s
    return _SESSION


def fetch(url: str, cache_name: str, *, binary: bool = False,
          force: bool = False, pause: float = 0.4) -> bytes | str:
    """GET ``url``, caching the raw payload at data/raw/<cache_name>."""
    path: Path = RAW / cache_name
    if path.exists() and not force:
        return path.read_bytes() if binary else path.read_text(
            encoding="utf-8", errors="replace")

    resp = session().get(url, timeout=60)
    resp.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(resp.content)
    time.sleep(pause)  # be a good citizen
    return resp.content if binary else resp.content.decode("utf-8", "replace")
