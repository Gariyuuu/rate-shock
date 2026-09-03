"""Robustness battery.

Every estimate produced here is persisted to a single tidy table
(``results/tables/robustness_all.csv``) so that no specification is run and
quietly discarded. Each row carries the sample filter, window, return
definition, shock measure and inflation threshold that produced it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from .config import (BETA_SCALE_BPS, COVID_END, COVID_START, DAILY_WINDOWS,
                     INFLATION_THRESHOLD, INFLATION_THRESHOLD_ALTS, MARCH_2020,
                     PRIMARY_WINDOW, RANDOM_SEED, default_dep)
from .regressions import interaction_betas, primary_betas


# ---------------------------------------------------------------------------
# Sample filters
# ---------------------------------------------------------------------------
def sample_filters(df: pd.DataFrame) -> dict[str, pd.Series]:
    d = df["meeting_date"]
    keep_all = pd.Series(True, index=df.index)
    largest = _largest_surprise_id(df)
    return {
        "baseline": keep_all,
        "ex_emergency": df["emergency"] != True,             # noqa: E712
        "ex_march2020": d.dt.strftime("%Y-%m") != MARCH_2020,
        "ex_covid": ~((d >= COVID_START) & (d <= COVID_END)),
        "ex_largest_surprise": df["meeting_id"] != largest,
        "scheduled_only": df["scheduled"] == True,           # noqa: E712
        "post_2008": d >= "2009-01-01",
        "pre_2008": d < "2009-01-01",
    }


def _largest_surprise_id(df: pd.DataFrame) -> str:
    ev = df.drop_duplicates("meeting_id")[["meeting_id", "surprise_bps"]].dropna()
    if ev.empty:
        return ""
    return ev.loc[ev["surprise_bps"].abs().idxmax(), "meeting_id"]


# ---------------------------------------------------------------------------
# Inference robustness
# ---------------------------------------------------------------------------
def wild_bootstrap_p(y: pd.Series, x: pd.Series, n_boot: int = 2000,
                     seed: int = RANDOM_SEED) -> float:
    """Rademacher wild bootstrap p-value for H0: slope = 0.

    Imposes the null, which is the appropriate small-sample choice here.
    """
    ok = y.notna() & x.notna()
    y, x = y[ok].to_numpy(), x[ok].to_numpy()
    if len(y) < 20:
        return np.nan
    X = np.column_stack([np.ones(len(x)), x])
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    resid_full = y - X @ b
    se = _robust_se(X, resid_full)[1]
    t_obs = abs(b[1] / se) if se > 0 else np.nan

    # restricted model: y = a + e
    a = y.mean()
    r0 = y - a
    rng = np.random.default_rng(seed)
    count = 0
    for _ in range(n_boot):
        v = rng.choice([-1.0, 1.0], size=len(y))
        yb = a + r0 * v
        bb = np.linalg.lstsq(X, yb, rcond=None)[0]
        rb = yb - X @ bb
        seb = _robust_se(X, rb)[1]
        if seb > 0 and abs(bb[1] / seb) >= t_obs:
            count += 1
    return (count + 1) / (n_boot + 1)


def _robust_se(X: np.ndarray, resid: np.ndarray) -> np.ndarray:
    n, k = X.shape
    XtX_inv = np.linalg.inv(X.T @ X)
    meat = X.T @ np.diag(resid ** 2) @ X
    cov = XtX_inv @ meat @ XtX_inv * (n / max(n - k, 1))   # HC1
    return np.sqrt(np.diag(cov))


# ---------------------------------------------------------------------------
# Battery
# ---------------------------------------------------------------------------
def run_battery(df: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """All primary-beta specifications; returns one long tidy table."""
    rows = []
    filters = sample_filters(df)

    for fname, mask in filters.items():
        sub = df[mask]
        if sub.empty:
            continue
        for window in DAILY_WINDOWS:
            for shock in ("surprise_bps", "surprise_orth_bps"):
                for dep in ("auto", "car_raw", "car_adj"):
                    r = primary_betas(sub, window=window, dep=dep, shock=shock,
                                      label=fname)
                    if r.empty:
                        continue
                    r["sample"] = fname
                    r["dep_mode"] = dep
                    rows.append(r)

    # Inference variants on the baseline specification only.
    for cov in ("HC3", "HC0"):
        r = primary_betas(df, window=PRIMARY_WINDOW, cov=cov,
                          label=f"baseline_{cov}")
        r["sample"] = "baseline"
        r["dep_mode"] = "auto"
        rows.append(r)

    out = pd.concat(rows, ignore_index=True)
    return out


def run_interaction_battery(df: pd.DataFrame, events: pd.DataFrame,
                            build_fn) -> pd.DataFrame:
    """Interaction estimates across inflation thresholds and sample filters.

    ``build_fn(threshold)`` must return an analysis panel re-built with that
    high-inflation cutoff, because the regime dummy has to be recomputed from
    the release-aligned CPI series rather than re-thresholded after the fact.
    """
    rows = []
    thresholds = [INFLATION_THRESHOLD] + list(INFLATION_THRESHOLD_ALTS)
    for thr in thresholds:
        d = build_fn(thr)
        for fname, mask in sample_filters(d).items():
            if fname not in ("baseline", "ex_emergency", "ex_covid"):
                continue
            sub = d[mask]
            for window in (PRIMARY_WINDOW, "m1_p1"):
                r = interaction_betas(sub, window=window,
                                      label=f"{fname}_thr{thr}")
                if r.empty:
                    continue
                r["threshold"] = thr
                r["sample"] = fname
                rows.append(r)

    # Threshold-free alternative: split at the in-sample median CPI YoY.
    d = build_fn(INFLATION_THRESHOLD)
    med = events["latest_cpi_yoy"].median()
    d2 = d.copy()
    d2["high_inflation"] = (d2["latest_cpi_yoy"] >= med).astype(float)
    r = interaction_betas(d2, label=f"median_split_{med:.2f}")
    r["threshold"] = float(med)
    r["sample"] = "median_split"
    rows.append(r)

    return pd.concat(rows, ignore_index=True)


def bootstrap_table(df: pd.DataFrame, window: str = PRIMARY_WINDOW,
                    shock: str = "surprise_bps") -> pd.DataFrame:
    """Wild-bootstrap p-values for the baseline betas."""
    rows = []
    sub = df[df["window"] == window]
    for tk, g in sub.groupby("ticker"):
        dep = default_dep(tk)
        if tk == "SPY" and dep == "car_adj":
            continue
        p = wild_bootstrap_p(g[dep], g[shock])
        rows.append({"ticker": tk, "window": window, "shock": shock,
                     "wild_bootstrap_p": p, "n": int(g[dep].notna().sum())})
    return pd.DataFrame(rows)
