"""Build the FOMC event database.

Three independent sources are combined:

1. **Announcement timing + surprises** -- Bauer & Swanson (2023), updated series
   hosted by the Federal Reserve Bank of San Francisco. Provides the exact
   announcement date, the announcement time (from Swanson & Jayawickrema 2024),
   an ``Unscheduled`` flag, and the high-frequency policy surprise.
2. **Official announcement history** -- federalreserve.gov FOMC calendars, used
   purely to *validate* the dates above. Nothing is silently dropped.
3. **Target rate levels** -- FRED DFEDTAR (pre-Dec-2008) and DFEDTARU/DFEDTARL
   (the corridor era), used to compute the *raw* target change in bp.
"""
from __future__ import annotations

import io
import re

import numpy as np
import pandas as pd

from .config import INTERIM, MPS_TO_BPS, RAW, SAMPLE_END, SAMPLE_START
from .http_util import fetch

FRBSF_MPS_URL = (
    "https://www.frbsf.org/wp-content/uploads/monetary-policy-surprises-data.xlsx"
)
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"

SURPRISE_SOURCE = (
    "Bauer & Swanson (2023), 'A Reassessment of Monetary Policy Surprises and "
    "High-Frequency Identification', NBER Macroeconomics Annual 37; updated "
    "series (through 2023-12-13) published by the Federal Reserve Bank of San "
    "Francisco. MPS = first principal component of 30-minute changes in ED1-ED4 "
    "Eurodollar futures (SOFR futures SFR2-SFR5 from Jan 2023), scaled so the "
    "loading on the four-quarter-ahead contract is unity."
)


# ---------------------------------------------------------------------------
# 1. Surprises
# ---------------------------------------------------------------------------
def load_surprises(force: bool = False) -> pd.DataFrame:
    """Load the Bauer-Swanson FOMC-level surprise series."""
    raw = fetch(FRBSF_MPS_URL, "frbsf_monetary_policy_surprises.xlsx",
                binary=True, force=force)
    df = pd.read_excel(io.BytesIO(raw), sheet_name="FOMC (update 2023)")
    df = df.rename(columns={
        "Date": "meeting_date", "Time": "announcement_time",
        "Unscheduled": "unscheduled",
    })
    df["meeting_date"] = pd.to_datetime(df["meeting_date"])

    # MPS/MPS_ORTH arrive in percentage points; convert to basis points.
    df["surprise_bps"] = df["MPS"] * MPS_TO_BPS
    df["surprise_orth_bps"] = df["MPS_ORTH"] * MPS_TO_BPS
    # Treasury-yield and equity responses in the same 30-minute window are kept
    # for the intraday cross-check (they are NOT mixed with daily returns).
    for c in ("TNOTE02", "TNOTE10", "TBOND"):
        df[f"hf_{c.lower()}_bps"] = df[c] * MPS_TO_BPS

    keep = ["meeting_date", "announcement_time", "unscheduled", "surprise_bps",
            "surprise_orth_bps", "hf_tnote02_bps", "hf_tnote10_bps",
            "hf_tbond_bps", "ED4", "SP500 emini"]
    return df[keep].sort_values("meeting_date").reset_index(drop=True)


# ---------------------------------------------------------------------------
# 2. Official Fed announcement history (validation only)
# ---------------------------------------------------------------------------
def official_fed_dates(start_year: int = 1998,
                       end_year: int = 2024) -> dict[pd.Timestamp, str]:
    """Scrape FOMC dates from the Fed's own calendar pages.

    The Board has used several URL layouts over the years, and for a few years
    the historical calendar links only the minutes/meeting materials rather than
    the statement. We therefore collect two tiers of evidence and record which
    one confirmed each date:

    ``statement``  -- a press-release URL for the policy statement itself.
    ``meeting``    -- minutes / meeting-material URL, i.e. the date the FOMC met.

    For a scheduled meeting the statement is released on the final meeting day,
    so a ``meeting`` match is still a genuine confirmation of the date.
    """
    found: dict[pd.Timestamp, str] = {}
    pages = [("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
              "fed_cal_current.html")]
    pages += [
        (f"https://www.federalreserve.gov/monetarypolicy/fomchistorical{y}.htm",
         f"fed_cal_{y}.html")
        for y in range(start_year, end_year + 1)
    ]
    statement_pats = [
        r"/boarddocs/press/monetary/\d{4}/(\d{8})",     # 2002-2005
        r"/boarddocs/press/general/\d{4}/(\d{8})",      # 1999-2001
        r"/newsevents/press/monetary/(\d{8})a\.htm",    # 2006-2010
        r"/newsevents/pressreleases/monetary(\d{8})a1?\.htm",  # 2011-
    ]
    meeting_pats = [
        r"/fomc/minutes/(\d{8})\.htm",
        r"/monetarypolicy/fomcminutes(\d{8})\.htm",
        r"/monetarypolicy/files/FOMC(\d{8})meeting\.pdf",
        r"/monetarypolicy/files/FOMC(\d{8})material\.(?:pdf|htm)",
    ]
    for url, cache in pages:
        try:
            html = fetch(url, cache)
        except Exception:
            continue  # not every year has a historical page
        for tier, pats in (("statement", statement_pats), ("meeting", meeting_pats)):
            for pat in pats:
                for d in re.findall(pat, html):
                    try:
                        ts = pd.Timestamp(d)
                    except ValueError:
                        continue
                    # never downgrade a statement-tier confirmation
                    if found.get(ts) != "statement":
                        found[ts] = tier
    return found


MONETARY_TITLE_RE = re.compile(
    r"FOMC statement|federal funds|discount rate|monetary policy|"
    r"liquidity arrangement|swap line|asset purchase|securities holdings|"
    r"open market operation|policy rate|target range",
    re.I)


def verify_date_directly(ts: pd.Timestamp) -> tuple[str, str] | None:
    """Check one date against the Board's monetary press-release archive.

    Unscheduled announcements are not always linked from the historical FOMC
    calendar pages. The Board publishes same-day releases under an a/b/c
    suffix, and not all of them are monetary actions (bank-regulatory notices
    share the path), so we enumerate the suffixes, read each release TITLE, and
    only accept one whose title describes a monetary policy action. The
    matched title is returned and stored in the event database so the decision
    is auditable rather than buried in a regex.
    """
    d = ts.strftime("%Y%m%d")
    templates = [
        "https://www.federalreserve.gov/newsevents/press/monetary/{d}{s}.htm",
        "https://www.federalreserve.gov/newsevents/pressreleases/monetary{d}{s}.htm",
    ]
    for suffix in ("a", "b", "c", "d"):
        for tmpl in templates:
            try:
                html = fetch(tmpl.format(d=d, s=suffix), f"fed_press_{d}{suffix}.html")
            except Exception:
                continue
            m = re.search(r"<title>(.*?)</title>", html, re.S)
            title = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
            title = title.replace("Federal Reserve Board - ", "")
            if MONETARY_TITLE_RE.search(title):
                return "press_release", title
    return None


def official_announcement_dates(**kw) -> set[pd.Timestamp]:
    """Backwards-compatible set of all officially confirmed FOMC dates."""
    return set(official_fed_dates(**kw))


# ---------------------------------------------------------------------------
# 3. Target rate levels
# ---------------------------------------------------------------------------
def _fred(series_id: str, force: bool = False) -> pd.Series:
    txt = fetch(FRED_CSV.format(sid=series_id), f"fred_{series_id}.csv",
                force=force)
    df = pd.read_csv(io.StringIO(txt))
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna().set_index("date")["value"].sort_index()


def target_rate_series(force: bool = False) -> pd.Series:
    """Daily fed funds target (midpoint of the corridor after Dec 2008)."""
    old = _fred("DFEDTAR", force)                    # single target, ->2008-12-15
    up = _fred("DFEDTARU", force)                    # corridor upper, 2008-12-16->
    lo = _fred("DFEDTARL", force)
    mid = ((up + lo) / 2.0).dropna()
    combined = pd.concat([old[~old.index.isin(mid.index)], mid]).sort_index()
    return combined.asfreq("D").ffill()


# ---------------------------------------------------------------------------
# Event database
# ---------------------------------------------------------------------------
def build_event_database(force: bool = False) -> pd.DataFrame:
    surp = load_surprises(force=force)
    target = target_rate_series(force=force)
    official = official_fed_dates()

    ev = surp.copy()
    ev["meeting_id"] = ev["meeting_date"].dt.strftime("FOMC%Y%m%d")

    # Announcement timestamp = date + the Swanson-Jayawickrema announcement time.
    ev["announcement_timestamp"] = pd.to_datetime(
        ev["meeting_date"].dt.strftime("%Y-%m-%d") + " "
        + ev["announcement_time"].astype(str).str.upper().str.replace(
            r"(AM|PM)", r" \1", regex=True),
        format="%Y-%m-%d %I:%M %p", errors="coerce")

    ev["scheduled"] = ev["unscheduled"] == 0
    ev["emergency"] = ev["unscheduled"] == 1

    # Raw target change: level on the announcement day vs the preceding day.
    def _lookup(ts, offset_days):
        d = ts - pd.Timedelta(days=offset_days)
        s = target.loc[:d]
        return float(s.iloc[-1]) if len(s) else np.nan

    ev["target_after"] = ev["meeting_date"].map(lambda d: _lookup(d, 0))
    ev["target_before"] = ev["meeting_date"].map(lambda d: _lookup(d, 1))
    ev["raw_change_bps"] = (ev["target_after"] - ev["target_before"]) * 100.0

    ev["surprise_source"] = np.where(
        ev["surprise_bps"].notna(), "BauerSwanson2023_MPS_FRBSF", "unavailable")
    ev["official_source"] = ev["meeting_date"].map(official).fillna("unmatched")
    # Unscheduled announcements are often absent from the calendar pages; probe
    # the press-release archive directly for anything still unmatched.
    ev["official_release_title"] = ""
    for i in ev.index[ev["official_source"] == "unmatched"]:
        got = verify_date_directly(ev.at[i, "meeting_date"])
        if got:
            ev.at[i, "official_source"], ev.at[i, "official_release_title"] = got
    ev["date_validated_official"] = ev["official_source"] != "unmatched"

    cols = ["meeting_id", "meeting_date", "announcement_timestamp", "scheduled",
            "emergency", "target_before", "target_after", "raw_change_bps",
            "surprise_bps", "surprise_orth_bps", "surprise_source",
            "date_validated_official", "official_source", "official_release_title", "hf_tnote02_bps", "hf_tnote10_bps",
            "hf_tbond_bps"]
    ev = ev[cols].sort_values("meeting_date").reset_index(drop=True)
    return ev


def in_sample(ev: pd.DataFrame) -> pd.DataFrame:
    m = (ev["meeting_date"] >= SAMPLE_START) & (ev["meeting_date"] <= SAMPLE_END)
    return ev.loc[m].reset_index(drop=True)


if __name__ == "__main__":
    ev = build_event_database()
    ev.to_csv(INTERIM / "fomc_events_full.csv", index=False)
    print(ev.tail(8).to_string())
