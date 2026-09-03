"""Event-study regressions: primary betas and inflation-regime interactions.

Inference
---------
Standard errors are heteroskedasticity-robust (HC1). FOMC announcements are
spaced roughly six weeks apart and each observation is a short, non-overlapping
window, so there is no mechanical overlap-induced autocorrelation to correct
for; the robustness module additionally reports HC3 and a wild bootstrap, which
matter more than HC1-vs-HAC at these sample sizes.

Scaling
-------
``surprise_bps`` is in basis points, so the raw slope is "percent per 1bp".
Everything reported to the reader is rescaled to **percent per 25bp** so the
numbers are interpretable as a typical policy increment.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from .config import BETA_SCALE_BPS, PRIMARY_WINDOW, default_dep


def _fit(y: pd.Series, X: pd.DataFrame, cov: str = "HC1"):
    X = sm.add_constant(X, has_constant="add")
    ok = y.notna() & X.notna().all(axis=1)
    if ok.sum() < 10:
        return None, ok.sum()
    return sm.OLS(y[ok], X[ok]).fit(cov_type=cov), int(ok.sum())


def _tidy(res, term: str, scale: float) -> dict:
    """Rescaled coefficient with robust SE, CI and p-value."""
    b = res.params[term] * scale
    se = res.bse[term] * scale
    lo, hi = (res.conf_int().loc[term] * scale).tolist()
    return {"beta": b, "se": se, "ci_low": lo, "ci_high": hi,
            "t": res.tvalues[term], "p": res.pvalues[term]}


def merge_panel(panel: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Attach event-level regressors to the (event, ticker, window) panel."""
    keep = ["meeting_id", "surprise_bps", "surprise_orth_bps", "raw_change_bps",
            "emergency", "scheduled", "high_inflation", "latest_cpi_yoy",
            "latest_core_cpi_yoy", "meeting_date"]
    keep = [c for c in keep if c in events.columns]
    return panel.merge(events[keep].drop(columns=["meeting_date"], errors="ignore"),
                       on="meeting_id", how="left")


def primary_betas(df: pd.DataFrame, *, window: str = PRIMARY_WINDOW,
                  dep: str = "auto", shock: str = "surprise_bps",
                  cov: str = "HC1", label: str = "primary") -> pd.DataFrame:
    """AR_i = alpha_i + beta_i * Shock + eps, estimated per asset."""
    out = []
    sub = df[df["window"] == window]
    for tk, g in sub.groupby("ticker"):
        dcol = default_dep(tk) if dep == "auto" else dep
        res, n = _fit(g[dcol], g[[shock]], cov=cov)
        if res is None:
            out.append({"ticker": tk, "n": n, "spec": label, "window": window,
                        "dep": dcol, "shock": shock, "beta": np.nan})
            continue
        row = {"ticker": tk, "n": n, "spec": label, "window": window,
               "dep": dcol, "shock": shock, "cov_type": cov,
               "alpha": res.params["const"], "r2": res.rsquared}
        row.update(_tidy(res, shock, BETA_SCALE_BPS))
        out.append(row)
    return pd.DataFrame(out).sort_values("beta").reset_index(drop=True)


def interaction_betas(df: pd.DataFrame, *, window: str = PRIMARY_WINDOW,
                      dep: str = "auto", shock: str = "surprise_bps",
                      regime: str = "high_inflation", cov: str = "HC1",
                      label: str = "interaction") -> pd.DataFrame:
    """AR = a + b1*Shock + b2*High + b3*Shock*High + eps."""
    out = []
    sub = df[df["window"] == window].copy()
    sub["_x"] = sub[shock] * sub[regime]
    for tk, g in sub.groupby("ticker"):
        dcol = default_dep(tk) if dep == "auto" else dep
        X = g[[shock, regime, "_x"]]
        res, n = _fit(g[dcol], X, cov=cov)
        if res is None:
            out.append({"ticker": tk, "n": n, "spec": label, "window": window})
            continue
        row = {"ticker": tk, "n": n, "spec": label, "window": window,
               "dep": dcol, "shock": shock, "regime": regime, "cov_type": cov,
               "r2": res.rsquared,
               "n_high": int(g[regime].sum()), "n_low": int((g[regime] == 0).sum())}
        for name, term in (("shock", shock), ("high", regime), ("inter", "_x")):
            sc = BETA_SCALE_BPS if name in ("shock", "inter") else 1.0
            t = _tidy(res, term, sc)
            row.update({f"{name}_{k}": v for k, v in t.items()})
        # Implied sensitivity inside each regime, with a correct SE for the sum.
        cvec = np.zeros(len(res.params))
        cvec[list(res.params.index).index(shock)] = 1.0
        cvec[list(res.params.index).index("_x")] = 1.0
        tt = res.t_test(cvec)
        row["beta_high_regime"] = float(np.squeeze(tt.effect)) * BETA_SCALE_BPS
        row["beta_high_regime_se"] = float(np.squeeze(tt.sd)) * BETA_SCALE_BPS
        row["beta_high_regime_p"] = float(np.squeeze(tt.pvalue))
        row["beta_low_regime"] = row["shock_beta"]
        out.append(row)
    return pd.DataFrame(out).reset_index(drop=True)


def pooled_test(df: pd.DataFrame, tickers: list[str], *,
                window: str = PRIMARY_WINDOW, dep: str = "car_adj",
                shock: str = "surprise_bps") -> pd.DataFrame:
    """Pooled regression across a group of assets, clustered by event.

    Used to ask whether a *group* (e.g. long-duration sectors) responds, which
    has more power than any single-asset test.
    """
    sub = df[(df["window"] == window) & (df["ticker"].isin(tickers))].copy()
    X = sm.add_constant(sub[[shock]], has_constant="add")
    ok = sub[dep].notna() & X.notna().all(axis=1)
    res = sm.OLS(sub[dep][ok], X[ok]).fit(
        cov_type="cluster", cov_kwds={"groups": sub["meeting_id"][ok]})
    row = {"group": ",".join(tickers), "n": int(ok.sum()),
           "n_events": sub["meeting_id"][ok].nunique(), "r2": res.rsquared}
    row.update(_tidy(res, shock, BETA_SCALE_BPS))
    return pd.DataFrame([row])
