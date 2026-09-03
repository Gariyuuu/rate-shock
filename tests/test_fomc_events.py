"""FOMC event database: dates, emergency tags, target changes."""
import pandas as pd
import pytest

from rateshock.config import SAMPLE_END, SAMPLE_START

# Independently known announcement dates and target moves. These are checked
# against the assembled database rather than against the source it came from.
# NOTE on 2008-12-16: the target moved from a 1.00% point target to a 0-0.25%
# RANGE. We summarise the corridor by its midpoint throughout, so that move is
# -87.5bp (1.00 -> 0.125), not the -75bp you get reading the upper bound.
KNOWN_MOVES = [
    ("2008-01-22", -75, True),      # emergency intermeeting cut
    ("2008-12-16", -87.5, False),   # to the 0-0.25 corridor, midpoint basis
    ("2020-03-15", -100, True),   # Sunday emergency cut to zero
    ("2020-03-03", -50, True),      # emergency intermeeting cut
    ("2022-06-15", +75, False),     # first 75bp hike of the cycle
    ("2022-03-16", +25, False),     # 2022 lift-off
    ("2015-12-16", +25, False),     # first hike after ZIRP
    ("2007-08-17", 0, True),        # discount-rate action, no FFR target change
]


def test_all_dates_validated_against_official_sources(data):
    ev = data["events"]
    assert ev["date_validated_official"].all(), (
        "unvalidated dates: "
        f"{ev.loc[~ev['date_validated_official'], 'meeting_date'].tolist()}")


def test_known_announcement_dates_present(data):
    dates = set(data["events"]["meeting_date"])
    for d, _, _ in KNOWN_MOVES:
        assert pd.Timestamp(d) in dates, f"missing FOMC announcement {d}"


def test_raw_target_changes_match_history(data):
    ev = data["events"].set_index("meeting_date")
    for d, bps, _ in KNOWN_MOVES:
        got = ev.loc[pd.Timestamp(d), "raw_change_bps"]
        assert abs(got - bps) < 1e-6, f"{d}: expected {bps}bp, got {got}"


def test_emergency_flags(data):
    ev = data["events"].set_index("meeting_date")
    for d, _, emergency in KNOWN_MOVES:
        assert bool(ev.loc[pd.Timestamp(d), "emergency"]) is emergency, d
    # scheduled and emergency must partition the sample
    assert (data["events"]["scheduled"] ^ data["events"]["emergency"]).all()


def test_no_duplicate_meetings(data):
    ev = data["events"]
    assert ev["meeting_id"].is_unique
    assert ev["meeting_date"].is_unique


def test_sample_bounds_and_ordering(data):
    ev = data["events"]
    assert ev["meeting_date"].min() >= pd.Timestamp(SAMPLE_START)
    assert ev["meeting_date"].max() <= pd.Timestamp(SAMPLE_END)
    assert ev["meeting_date"].is_monotonic_increasing


def test_announcement_timestamp_has_intraday_time(data):
    ts = data["events"]["announcement_timestamp"].dropna()
    assert len(ts) == len(data["events"]), "every event needs a timestamp"
    # Announcements are released at a real time of day, never at midnight.
    # The window is wide on purpose: the 2008-10-08 coordinated global rate cut
    # was announced at 07:00 ET and 2020-03-15 at 17:00 ET.
    assert (ts.dt.hour > 0).all()
    assert ts.dt.hour.between(6, 22).all(), (
        ts[~ts.dt.hour.between(6, 22)].tolist())


def test_surprise_source_is_recorded(data):
    ev = data["events"]
    src = ev.loc[ev["surprise_bps"].notna(), "surprise_source"].unique()
    assert list(src) == ["BauerSwanson2023_MPS_FRBSF"]


def test_raw_change_is_not_the_surprise(data):
    """The identifying premise: a rate change is not a rate surprise."""
    ev = data["events"].dropna(subset=["surprise_bps", "raw_change_bps"])
    corr = ev[["raw_change_bps", "surprise_bps"]].corr().iloc[0, 1]
    assert abs(corr) < 0.75, (
        "raw change and surprise are nearly collinear; the two would be "
        f"interchangeable (corr={corr:.2f})")
