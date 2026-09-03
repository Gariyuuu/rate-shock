"""Assemble the analysis dataset from the raw ingest modules."""
from __future__ import annotations

import pandas as pd

from .config import (ALL_TICKERS, INFLATION_THRESHOLD, PROCESSED)
from .cpi import attach_inflation_regime, cpi_releases
from .events import build_window_panel, event_time_paths
from .fomc import build_event_database, in_sample
from .prices import download_prices
from .regressions import merge_panel


def build(threshold: float = INFLATION_THRESHOLD, save: bool = True):
    events = in_sample(build_event_database())
    releases = cpi_releases()
    events = attach_inflation_regime(events, releases, threshold=threshold)

    prices = download_prices()
    panel = build_window_panel(events, prices, ALL_TICKERS)
    df = merge_panel(panel, events)

    if save:
        events.to_csv(PROCESSED / "fomc_events.csv", index=False)
        panel.to_csv(PROCESSED / "event_panel.csv", index=False)
        df.to_csv(PROCESSED / "analysis_panel.csv", index=False)
    return events, prices, panel, df


def paths(events: pd.DataFrame, prices: pd.DataFrame, tickers=None):
    return event_time_paths(events, prices, tickers or ALL_TICKERS)
