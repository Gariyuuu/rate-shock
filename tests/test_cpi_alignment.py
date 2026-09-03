"""CPI release-timing alignment.

The failure mode this guards against: attaching the CPI reading for the month
of the FOMC meeting, which was not published until weeks AFTER the meeting.
"""
import pandas as pd
import pytest

from rateshock.cpi import attach_inflation_regime


# Independently known CPI release dates and headline YoY prints.
KNOWN_RELEASES = [
    ("2022-06-01", "2022-07-13", 9.06),   # the 9.1% peak print
    ("2021-04-01", "2021-05-12", 4.16),
    ("2008-07-01", "2008-08-14", 5.60),
]


def test_release_dates_match_known_bls_releases(releases):
    r = releases.set_index("reference_month")
    for ref, rel, yoy in KNOWN_RELEASES:
        row = r.loc[pd.Timestamp(ref)]
        assert row["release_date"] == pd.Timestamp(rel), (
            f"{ref}: expected release {rel}, got {row['release_date'].date()}")
        assert row["cpi_yoy"] == pytest.approx(yoy, abs=0.05)


def test_release_always_follows_reference_month(releases):
    assert (releases["release_date"] > releases["reference_month"]).all()
    lag = (releases["release_date"] - releases["reference_month"]).dt.days
    # CPI for month M is published in the middle of month M+1.
    assert lag.min() >= 30
    assert lag.max() <= 75


def test_no_lookahead_cpi_is_ever_used(data):
    """Every attached CPI must have been RELEASED before the announcement."""
    ev = data["events"].dropna(subset=["cpi_release_timestamp"])
    assert (ev["cpi_release_timestamp"]
            <= ev["announcement_timestamp"]).all()
    assert (ev["cpi_lag_days"] >= 0).all()


def test_attached_cpi_is_the_most_recent_available(data, releases):
    """Not just any prior release -- the LATEST one."""
    ev = data["events"].dropna(subset=["cpi_reference_month"])
    rel = releases.sort_values("release_timestamp")
    for _, e in ev.sample(40, random_state=0).iterrows():
        avail = rel[rel["release_timestamp"] <= e["announcement_timestamp"]]
        assert avail.iloc[-1]["reference_month"] == e["cpi_reference_month"]


def test_reference_month_is_never_the_meeting_month_or_later(data):
    ev = data["events"].dropna(subset=["cpi_reference_month"])
    ref = ev["cpi_reference_month"].dt.to_period("M")
    meet = ev["meeting_date"].dt.to_period("M")
    assert (ref < meet).all(), "CPI reference month must precede the meeting"


def test_same_day_cpi_release_counts_as_known(data, releases):
    """CPI prints at 08:30 ET; an FOMC statement lands at 14:00 the same day.

    A CPI release on the morning of an FOMC day IS in the information set, so
    the lag should be a fraction of a day, not pushed to the previous month.
    """
    ev = data["events"]
    same_day = ev[ev["cpi_lag_days"] < 1.0]
    assert len(same_day) > 0, "expected at least one same-day CPI/FOMC pairing"
    assert (same_day["cpi_lag_days"] > 0).all()


def test_threshold_changes_regime_assignment(data, releases):
    ev = data["events"]
    lo = attach_inflation_regime(
        ev.drop(columns=[c for c in ev.columns
                         if c.startswith(("cpi_", "latest_", "high_"))]),
        releases, threshold=2.0)
    hi = attach_inflation_regime(
        ev.drop(columns=[c for c in ev.columns
                         if c.startswith(("cpi_", "latest_", "high_"))]),
        releases, threshold=4.0)
    assert lo["high_inflation"].sum() > hi["high_inflation"].sum()


def test_regime_has_both_states_with_usable_counts(data):
    ev = data["events"]
    n_hi = int(ev["high_inflation"].sum())
    n_lo = int((ev["high_inflation"] == 0).sum())
    assert n_hi >= 30 and n_lo >= 30, (n_hi, n_lo)


def test_high_inflation_regime_is_not_only_the_2021_episode(data):
    """Guards the interpretation: the regime must not be a 2021-23 dummy."""
    ev = data["events"]
    yrs = set(ev.loc[ev["high_inflation"] == 1, "meeting_date"].dt.year)
    assert len(yrs - {2021, 2022, 2023}) >= 3, sorted(yrs)
