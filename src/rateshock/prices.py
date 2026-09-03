"""Daily price data for sector ETFs, benchmarks and cross-assets."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import (ALL_TICKERS, OPTIONAL_ASSETS, RAW, SAMPLE_END,
                     SAMPLE_START)

# Pull a generous buffer either side of the sample so [-5,+5] windows on the
# first and last events are fully populated.
DOWNLOAD_START = "1998-01-01"
DOWNLOAD_END = "2024-06-30"


def download_prices(tickers: list[str] | None = None, *, force: bool = False,
                    include_optional: bool = True) -> pd.DataFrame:
    """Adjusted close prices, one column per ticker."""
    tickers = list(tickers or ALL_TICKERS)
    if include_optional:
        tickers += list(OPTIONAL_ASSETS)
    cache = RAW / "prices_adjclose.csv"
    if cache.exists() and not force:
        df = pd.read_csv(cache, index_col=0, parse_dates=True)
        if set(tickers).issubset(df.columns):
            return df

    import yfinance as yf
    raw = yf.download(tickers, start=DOWNLOAD_START, end=DOWNLOAD_END,
                      auto_adjust=True, progress=False, group_by="column",
                      threads=True)
    px = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    px = px[[t for t in tickers if t in px.columns]].sort_index()
    px.index = pd.to_datetime(px.index).tz_localize(None)
    px.to_csv(cache)
    return px


def log_returns(px: pd.DataFrame) -> pd.DataFrame:
    """Daily log returns in percent."""
    return np.log(px / px.shift(1)) * 100.0


def trading_calendar(px: pd.DataFrame) -> pd.DatetimeIndex:
    """Equity trading days, taken from SPY's own quote history."""
    spy = px["SPY"].dropna()
    return pd.DatetimeIndex(spy.index)


def coverage_table(px: pd.DataFrame) -> pd.DataFrame:
    """Per-ticker coverage measured on the EQUITY trading calendar.

    The frame's index is the union across all assets, which includes weekends
    because BTC-USD trades 24/7. Counting gaps against that union would
    misreport every equity series as missing ~1000 days, so coverage is
    evaluated on SPY's own trading days.
    """
    cal = trading_calendar(px)
    in_win = cal[(cal >= SAMPLE_START) & (cal <= SAMPLE_END)]
    rows = []
    for c in px.columns:
        s = px[c].dropna()
        if c in OPTIONAL_ASSETS:      # 24/7 asset: not on the equity calendar
            miss = np.nan
        else:
            live = in_win[in_win >= s.index.min()]
            miss = int(px.loc[live, c].isna().sum()) if len(live) else 0
        rows.append({"ticker": c, "first_obs": s.index.min(),
                     "last_obs": s.index.max(), "n_obs": len(s),
                     "inception_after_sample_start": s.index.min() > pd.Timestamp(SAMPLE_START),
                     "missing_days_after_inception": miss})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    px = download_prices()
    print(coverage_table(px).to_string(index=False))
