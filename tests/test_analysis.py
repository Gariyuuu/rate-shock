"""Estimation layer: scaling, interactions, clustering, robustness."""
import numpy as np
import pandas as pd
import pytest

from rateshock import cluster, crossasset, robustness
from rateshock.config import BETA_SCALE_BPS, PRIMARY_WINDOW
from rateshock.regressions import interaction_betas, primary_betas


def test_beta_is_scaled_per_25bp(data):
    """A beta reported per 25bp must be 25x the per-1bp slope."""
    import statsmodels.api as sm
    df = data["df"]
    g = df[(df["ticker"] == "IEF") & (df["window"] == PRIMARY_WINDOW)]
    ok = g["car_raw"].notna() & g["surprise_bps"].notna()
    raw = sm.OLS(g["car_raw"][ok],
                 sm.add_constant(g[["surprise_bps"]][ok])).fit(cov_type="HC1")
    rep = primary_betas(df).set_index("ticker").loc["IEF", "beta"]
    assert rep == pytest.approx(raw.params["surprise_bps"] * BETA_SCALE_BPS)
    assert BETA_SCALE_BPS == 25.0


def test_confidence_interval_brackets_the_point_estimate(data):
    r = primary_betas(data["df"]).dropna(subset=["beta"])
    assert (r["ci_low"] < r["beta"]).all()
    assert (r["beta"] < r["ci_high"]).all()
    # a 95% CI is ~ +/- 1.96 robust SEs
    width = (r["ci_high"] - r["ci_low"]) / r["se"]
    assert np.allclose(width, 2 * 1.959963985, atol=0.02)


def test_reported_n_matches_usable_observations(data):
    df = data["df"]
    r = primary_betas(df).set_index("ticker")
    for tk in ("XLF", "GLD", "XLRE"):
        g = df[(df["ticker"] == tk) & (df["window"] == PRIMARY_WINDOW)]
        dep = r.loc[tk, "dep"]
        expected = int((g[dep].notna() & g["surprise_bps"].notna()).sum())
        assert int(r.loc[tk, "n"]) == expected


def test_interaction_decomposes_into_regime_betas(data):
    """beta_high must equal beta_low + interaction, by construction."""
    inter = interaction_betas(data["df"]).dropna(subset=["inter_beta"])
    lhs = inter["beta_low_regime"] + inter["inter_beta"]
    assert np.allclose(lhs, inter["beta_high_regime"], atol=1e-8)


def test_interaction_regimes_both_populated(data):
    inter = interaction_betas(data["df"]).dropna(subset=["n_high"])
    assert (inter["n_high"] >= 15).all()
    assert (inter["n_low"] >= 15).all()


def test_r_squared_in_unit_interval(data):
    r = primary_betas(data["df"]).dropna(subset=["r2"])
    assert ((r["r2"] >= 0) & (r["r2"] <= 1)).all()


def test_response_matrix_shape_and_content(data):
    mat = crossasset.response_matrix(data["df"])
    assert mat.shape[0] > 150
    assert "XLF" in mat.columns and "TLT" in mat.columns
    assert mat.notna().sum().min() > 50


def test_correlation_matrix_is_valid(data):
    mat = crossasset.response_matrix(data["df"])
    c = crossasset.event_correlations(mat)
    vals = c.to_numpy()
    assert np.allclose(np.diag(vals), 1.0, equal_nan=True)
    finite = vals[np.isfinite(vals)]
    assert (finite >= -1.0001).all() and (finite <= 1.0001).all()
    assert np.allclose(vals, vals.T, equal_nan=True)


def test_pca_variance_ratios_are_ordered_and_bounded(data):
    mat = crossasset.response_matrix(data["df"])
    bal = cluster.balanced_matrix(mat)
    _, evr, _ = cluster.run_pca(bal)
    assert (evr.diff().dropna() <= 1e-12).all(), "components must be ordered"
    assert 0 < evr.sum() <= 1.0000001


def test_balanced_matrix_drops_short_history_assets(data):
    mat = crossasset.response_matrix(data["df"])
    bal = cluster.balanced_matrix(mat)
    assert "XLRE" not in bal.columns, "XLRE (2015 inception) must be excluded"
    assert not bal.isna().any().any()


def test_clustering_returns_one_label_per_asset(data):
    mat = crossasset.response_matrix(data["df"])
    bal = cluster.balanced_matrix(mat)
    _, labels, corr = cluster.cluster_assets(bal, n_clusters=4)
    assert set(labels.index) == set(bal.columns)
    assert labels.nunique() == 4


def test_largest_surprise_filter_removes_exactly_one_event(data):
    df = data["df"]
    f = robustness.sample_filters(df)
    removed = df.loc[~f["ex_largest_surprise"], "meeting_id"].nunique()
    assert removed == 1


def test_emergency_filter_removes_the_emergency_meetings(data):
    df = data["df"]
    f = robustness.sample_filters(df)
    kept = df[f["ex_emergency"]]
    assert not kept["emergency"].any()
    assert kept["meeting_id"].nunique() < df["meeting_id"].nunique()


def test_march_2020_filter(data):
    df = data["df"]
    f = robustness.sample_filters(df)
    kept = df[f["ex_march2020"]]
    assert not kept["meeting_date"].dt.strftime("%Y-%m").eq("2020-03").any()


def test_wild_bootstrap_returns_valid_pvalue(data):
    df = data["df"]
    g = df[(df["ticker"] == "IEF") & (df["window"] == PRIMARY_WINDOW)]
    p = robustness.wild_bootstrap_p(g["car_raw"], g["surprise_bps"], n_boot=400)
    assert 0.0 < p <= 1.0
    # IEF's bond-price response is the strongest prior in the study
    assert p < 0.10
