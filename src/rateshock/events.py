"""Event-window construction and abnormal returns.

Trading-day mapping
-------------------
Day 0 is the equity trading day on which the announcement occurs. FOMC
statements are released at 14:00 ET (17:00 ET for the 2020-03-15 Sunday
announcement, 11:30 ET pre-1994), always before the 16:00 ET equity close, so
the announcement-day close-to-close return contains the announcement. If an
announcement falls on a non-trading day, day 0 is the next trading day.

Window returns are sums of daily LOG returns (in percent), which makes them
additive across days and directly comparable across assets.

Abnormal return
---------------
``AR = CAR_asset - CAR_SPY`` over the identical window. This is a
market-adjusted (beta-of-one) abnormal return rather than a market-model
residual: with ~200 events and a very short window, estimating per-asset betas
on an estimation window adds noise and introduces its own look-back choices.
The raw (unadjusted) return is retained alongside so every result can be shown
both ways.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CAR_WINDOW, DAILY_WINDOWS


def map_to_trading_days(dates: pd.Series, calendar: pd.DatetimeIndex) -> pd.Series:
    """Index of day 0 in ``calendar`` for each announcement date."""
    cal = pd.DatetimeIndex(calendar).sort_values()
    # searchsorted 'left' gives the first trading day >= the announcement date,
    # which is the announcement day itself whenever markets are open.
    pos = cal.searchsorted(pd.DatetimeIndex(dates), side="left")
    pos = np.where(pos >= len(cal), -1, pos)
    return pd.Series(pos, index=dates.index)


def build_window_panel(events: pd.DataFrame, prices: pd.DataFrame,
                       tickers: list[str], benchmark: str = "SPY",
                       windows: dict | None = None) -> pd.DataFrame:
    """Long panel: one row per (event, ticker, window).

    Returns columns ``car_raw`` (asset's own cumulative log return, %) and
    ``car_adj`` (that minus the benchmark's over the same window).
    """
    windows = windows or DAILY_WINDOWS
    cal = pd.DatetimeIndex(prices[benchmark].dropna().index).sort_values()
    px_cal = prices.loc[cal]
    rets = np.log(px_cal / px_cal.shift(1)) * 100.0

    day0 = map_to_trading_days(events["meeting_date"], cal)
    cols = [t for t in tickers if t in rets.columns]
    arr = {t: rets[t].to_numpy() for t in cols}
    n = len(cal)

    rows = []
    for i, ev in events.iterrows():
        p0 = int(day0.iloc[i])
        if p0 < 0:
            continue
        for wname, (a, b) in windows.items():
            lo, hi = p0 + a, p0 + b
            if lo < 1 or hi >= n:      # need lo-1 for the first return
                continue
            bench = np.sum(arr[benchmark][lo:hi + 1])
            bench_ok = np.isfinite(arr[benchmark][lo:hi + 1]).all()
            for t in cols:
                seg = arr[t][lo:hi + 1]
                if not np.isfinite(seg).all():
                    continue           # asset not yet trading: drop, never zero-fill
                raw = float(np.sum(seg))
                rows.append({
                    "meeting_id": ev["meeting_id"],
                    "meeting_date": ev["meeting_date"],
                    "ticker": t,
                    "window": wname,
                    "car_raw": raw,
                    "car_adj": raw - float(bench) if bench_ok else np.nan,
                    "day0_index": p0,
                })
    return pd.DataFrame(rows)


def event_time_paths(events: pd.DataFrame, prices: pd.DataFrame,
                     tickers: list[str], benchmark: str = "SPY",
                     window: tuple[int, int] = CAR_WINDOW) -> pd.DataFrame:
    """Cumulative abnormal return by event-time day, for CAR curves.

    Cumulation starts at the beginning of the window, so relative day ``a``
    carries that day's own return and day ``b`` carries the full-window CAR.
    """
    cal = pd.DatetimeIndex(prices[benchmark].dropna().index).sort_values()
    rets = np.log(prices.loc[cal] / prices.loc[cal].shift(1)) * 100.0
    day0 = map_to_trading_days(events["meeting_date"], cal)
    a, b = window
    cols = [t for t in tickers if t in rets.columns]
    arr = {t: rets[t].to_numpy() for t in cols}
    bench = arr[benchmark]
    n = len(cal)

    rows = []
    for i, ev in events.iterrows():
        p0 = int(day0.iloc[i])
        if p0 < 0 or p0 + a < 1 or p0 + b >= n:
            continue
        for t in cols:
            seg = arr[t][p0 + a: p0 + b + 1]
            bseg = bench[p0 + a: p0 + b + 1]
            if not (np.isfinite(seg).all() and np.isfinite(bseg).all()):
                continue
            car = np.cumsum(seg - bseg)
            for k, rel in enumerate(range(a, b + 1)):
                rows.append({"meeting_id": ev["meeting_id"], "ticker": t,
                             "rel_day": rel, "car_adj": float(car[k]),
                             "ret_adj": float(seg[k] - bseg[k])})
    return pd.DataFrame(rows)


def wide_response_matrix(panel: pd.DataFrame, window: str) -> pd.DataFrame:
    """events x assets matrix of benchmark-adjusted responses for one window."""
    sub = panel[panel["window"] == window]
    return sub.pivot(index="meeting_id", columns="ticker", values="car_adj")
