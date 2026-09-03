"""Cross-asset event-response vectors and their correlation structure."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import PRIMARY_WINDOW, default_dep


def response_matrix(df: pd.DataFrame, window: str = PRIMARY_WINDOW,
                    tickers: list[str] | None = None) -> pd.DataFrame:
    """events x assets matrix, each asset on its own meaningful return basis.

    Sectors enter benchmark-adjusted; SPY and the cross-assets enter raw.
    """
    sub = df[df["window"] == window]
    tickers = tickers or sorted(sub["ticker"].unique())
    cols = {}
    for tk in tickers:
        g = sub[sub["ticker"] == tk].set_index("meeting_id")
        cols[tk] = g[default_dep(tk)]
    return pd.DataFrame(cols)


def event_correlations(mat: pd.DataFrame, min_overlap: int = 60) -> pd.DataFrame:
    """Pairwise correlation of event responses, pairwise-complete.

    Assets have different inception dates (GLD 2004, XLRE 2015), so pairwise
    deletion is used and any pair with fewer than ``min_overlap`` shared events
    is set to NaN rather than reported on thin overlap.
    """
    c = mat.corr(min_periods=min_overlap)
    n = mat.notna().astype(int).T.dot(mat.notna().astype(int))
    return c.where(n >= min_overlap)


def overlap_counts(mat: pd.DataFrame) -> pd.DataFrame:
    ind = mat.notna().astype(int)
    return ind.T.dot(ind)


def standardized_matrix(mat: pd.DataFrame) -> pd.DataFrame:
    """Z-score each asset's response across events (for PCA / clustering)."""
    return (mat - mat.mean()) / mat.std(ddof=1)
