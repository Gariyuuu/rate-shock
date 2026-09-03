"""Inflation regime construction with true release-date alignment.

The single most important detail in this file: at an FOMC announcement,
investors know the *most recently released* CPI report, not the CPI for the
month in which the meeting takes place. CPI for reference month M is published
in the middle of month M+1, and FOMC meetings frequently fall within days of a
CPI release -- sometimes before it, sometimes after. Merging on the calendar
month would therefore leak future information into the regime classification.

We avoid that by scraping BLS's own news-release archive, which links every
historical CPI release and states the reference month in the link text, so each
(reference month -> release date) pair is observed rather than assumed.

A convenient property of NSA CPI: the not-seasonally-adjusted index is not
revised, so the YoY rate computed today from CPIAUCNS for a given reference
month equals the number printed in the original release.
"""
from __future__ import annotations

import io
import re

import numpy as np
import pandas as pd

from .config import INFLATION_THRESHOLD, INTERIM
from .http_util import fetch

BLS_ARCHIVE_URL = "https://www.bls.gov/bls/news-release/cpi.htm"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"

# BLS publishes the CPI news release at 08:30 ET. FOMC statements land at
# 14:00 ET (11:30 ET in the pre-1994 era), so a CPI report released on the
# morning of an FOMC day IS in the market's information set.
CPI_RELEASE_TIME = pd.Timedelta(hours=8, minutes=30)

_MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], start=1)}


def _parse_release_date(token: str) -> pd.Timestamp | None:
    """cpi_01112024 -> 2024-01-11 ; cpi_121598 -> 1998-12-15."""
    if len(token) == 8:
        mm, dd, yyyy = token[:2], token[2:4], token[4:]
    elif len(token) == 6:
        mm, dd, yy = token[:2], token[2:4], token[4:]
        yyyy = f"19{yy}" if int(yy) >= 90 else f"20{yy}"
    else:
        return None
    try:
        return pd.Timestamp(f"{yyyy}-{mm}-{dd}")
    except ValueError:
        return None


def cpi_release_dates(force: bool = False) -> pd.DataFrame:
    """Observed (reference_month, release_date) pairs from the BLS archive."""
    html = fetch(BLS_ARCHIVE_URL, "bls_cpi_archive.html", force=force)
    rows = []
    for li in re.findall(r"<li>(.*?)</li>", html, flags=re.S):
        m = re.search(r"(January|February|March|April|May|June|July|August|"
                      r"September|October|November|December)\s+(\d{4})\s+"
                      r"Consumer Price Index", li)
        if not m:
            continue
        ref = pd.Timestamp(year=int(m.group(2)), month=_MONTHS[m.group(1)], day=1)
        tok = re.search(r"cpi_(\d{6,8})\.(?:htm|pdf|txt)", li)
        if not tok:
            continue
        rel = _parse_release_date(tok.group(1))
        if rel is None:
            continue
        rows.append({"reference_month": ref, "release_date": rel})

    df = (pd.DataFrame(rows)
          .drop_duplicates(subset="reference_month", keep="first")
          .sort_values("reference_month")
          .reset_index(drop=True))
    df["release_timestamp"] = df["release_date"] + CPI_RELEASE_TIME
    return df


def _fred(sid: str, force: bool = False) -> pd.Series:
    txt = fetch(FRED_CSV.format(sid=sid), f"fred_{sid}.csv", force=force)
    d = pd.read_csv(io.StringIO(txt))
    d.columns = ["date", "value"]
    d["date"] = pd.to_datetime(d["date"])
    d["value"] = pd.to_numeric(d["value"], errors="coerce")
    return d.dropna().set_index("date")["value"].sort_index()


def cpi_releases(force: bool = False) -> pd.DataFrame:
    """Release calendar joined to headline and core CPI year-over-year rates."""
    rel = cpi_release_dates(force=force)
    head = _fred("CPIAUCNS", force)   # headline, NSA (not revised)
    core = _fred("CPILFENS", force)   # core (ex food & energy), NSA

    out = rel.copy()
    out["cpi_index"] = out["reference_month"].map(head)
    out["cpi_yoy"] = out["reference_month"].map(
        lambda m: _yoy(head, m))
    out["core_cpi_yoy"] = out["reference_month"].map(lambda m: _yoy(core, m))
    return out.dropna(subset=["cpi_yoy"]).reset_index(drop=True)


def _yoy(s: pd.Series, month: pd.Timestamp) -> float:
    prev = month - pd.DateOffset(years=1)
    if month in s.index and prev in s.index:
        return float((s[month] / s[prev] - 1.0) * 100.0)
    return np.nan


def attach_inflation_regime(events: pd.DataFrame, releases: pd.DataFrame,
                            threshold: float = INFLATION_THRESHOLD
                            ) -> pd.DataFrame:
    """For each FOMC event, attach the LATEST CPI report already released.

    Uses an as-of (backward) merge on the release *timestamp* versus the
    announcement *timestamp*, so a CPI print on the morning of an FOMC day
    counts as known, while one released the following day does not.
    """
    ev = events.sort_values("announcement_timestamp").copy()
    rel = releases.sort_values("release_timestamp").copy()

    merged = pd.merge_asof(
        ev, rel[["release_timestamp", "reference_month", "cpi_yoy",
                 "core_cpi_yoy"]],
        left_on="announcement_timestamp", right_on="release_timestamp",
        direction="backward", allow_exact_matches=True)

    merged = merged.rename(columns={
        "reference_month": "cpi_reference_month",
        "release_timestamp": "cpi_release_timestamp",
        "cpi_yoy": "latest_cpi_yoy",
        "core_cpi_yoy": "latest_core_cpi_yoy"})
    merged["cpi_lag_days"] = (
        merged["announcement_timestamp"] - merged["cpi_release_timestamp"]
    ).dt.total_seconds() / 86400.0
    merged["high_inflation"] = (merged["latest_cpi_yoy"] >= threshold).astype(float)
    merged.loc[merged["latest_cpi_yoy"].isna(), "high_inflation"] = np.nan
    return merged


if __name__ == "__main__":
    r = cpi_releases()
    r.to_csv(INTERIM / "cpi_releases.csv", index=False)
    print(r.tail(6).to_string(index=False))
