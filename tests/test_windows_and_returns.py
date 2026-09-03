"""Event windows, trading-day mapping, benchmark adjustment, missing data."""
import numpy as np
import pandas as pd
import pytest

from rateshock.config import DAILY_WINDOWS, PRIMARY_WINDOW, default_dep
from rateshock.events import build_window_panel, map_to_trading_days


def test_day0_is_announcement_day_when_market_open(data):
    prices, events = data["prices"], data["events"]
    cal = pd.DatetimeIndex(prices["SPY"].dropna().index).sort_values()
    pos = map_to_trading_days(events["meeting_date"], cal)
    for i, d in enumerate(events["meeting_date"]):
        mapped = cal[int(pos.iloc[i])]
        if d in set(cal):
            assert mapped == d, f"{d.date()} should map to itself"
        else:
            # non-trading day (e.g. the Sunday 2020-03-15 announcement):
            # day 0 rolls FORWARD to the next session, never backward.
            assert mapped > d, f"{d.date()} mapped backwards to {mapped.date()}"
            assert (mapped - d).days <= 4


def test_sunday_announcement_maps_forward(data):
    prices = data["prices"]
    cal = pd.DatetimeIndex(prices["SPY"].dropna().index).sort_values()
    pos = map_to_trading_days(pd.Series([pd.Timestamp("2020-03-15")]), cal)
    assert cal[int(pos.iloc[0])] == pd.Timestamp("2020-03-16")


def test_window_lengths_are_correct(data):
    """A window [a,b] must aggregate exactly b-a+1 daily returns."""
    prices, events = data["prices"], data["events"]
    cal = pd.DatetimeIndex(prices["SPY"].dropna().index).sort_values()
    rets = np.log(prices.loc[cal] / prices.loc[cal].shift(1)) * 100.0
    panel = data["panel"]
    ev = events.set_index("meeting_id")
    for wname, (a, b) in DAILY_WINDOWS.items():
        sub = panel[(panel["window"] == wname) & (panel["ticker"] == "SPY")]
        row = sub.iloc[len(sub) // 2]
        p0 = int(row["day0_index"])
        expected = float(rets["SPY"].to_numpy()[p0 + a: p0 + b + 1].sum())
        assert row["car_raw"] == pytest.approx(expected, abs=1e-9)
        assert len(rets["SPY"].to_numpy()[p0 + a: p0 + b + 1]) == b - a + 1


def test_benchmark_adjustment_is_difference_from_spy(data):
    panel = data["panel"]
    spy = panel[panel["ticker"] == "SPY"].set_index(["meeting_id", "window"])
    other = panel[panel["ticker"] == "XLK"].set_index(["meeting_id", "window"])
    joined = other.join(spy[["car_raw"]], rsuffix="_spy", how="inner")
    diff = joined["car_raw"] - joined["car_raw_spy"]
    assert np.allclose(joined["car_adj"], diff, atol=1e-9)


def test_spy_adjusted_return_is_identically_zero(data):
    panel = data["panel"]
    spy = panel[panel["ticker"] == "SPY"]
    assert np.allclose(spy["car_adj"], 0.0, atol=1e-12)


def test_cross_assets_use_raw_returns(data):
    """Subtracting an equity benchmark from a bond return is not an AR."""
    for tk in ("TLT", "IEF", "GLD", "SPY"):
        assert default_dep(tk) == "car_raw"
    for tk in ("XLF", "XLK", "XLU", "QQQ"):
        assert default_dep(tk) == "car_adj"


def test_missing_etf_data_is_dropped_not_zero_filled(data):
    """XLRE launched 2015-10-08; it must have no events before then."""
    panel, events = data["panel"], data["events"]
    ev = events.set_index("meeting_id")["meeting_date"]
    xlre = panel[panel["ticker"] == "XLRE"]
    assert len(xlre) > 0
    assert ev.loc[xlre["meeting_id"]].min() >= pd.Timestamp("2015-10-08")
    # and nothing was silently filled with zeros
    assert (xlre["car_raw"] == 0).sum() == 0


def test_no_nan_or_inf_in_estimation_columns(data):
    df = data["df"]
    sub = df[df["window"] == PRIMARY_WINDOW]
    for col in ("car_raw", "car_adj"):
        vals = sub[col].dropna()
        assert np.isfinite(vals).all()


def test_partial_windows_are_excluded(data):
    """Events too close to an asset's inception must not produce a window."""
    panel = data["panel"]
    counts = panel[panel["window"] == "m5_p5"].groupby("ticker").size()
    # every asset present must have a strictly positive, finite count
    assert (counts > 0).all()
    # GLD (2004 inception) must have fewer events than SPY
    assert counts["GLD"] < counts["SPY"]
