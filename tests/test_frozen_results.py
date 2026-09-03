"""Frozen-result regression guard.

Added at project finalization (see README "Frozen scope"). The study's
conclusions are final; this file pins the headline estimates so that any future
refactor which silently moves a coefficient, a p-value, or -- most importantly
-- the sign or significance of a conclusion, fails loudly instead of quietly
rewriting the findings.

These values are NOT inputs to any computation. They are read back out of
results/ after `scripts/run_analysis.py` has regenerated it.

If a genuine implementation fix changes one of these, update the expectation
here AND the corresponding text in README.md / report/REPORT.md in the same
commit. Do not update one without the other.
"""
import json
from pathlib import Path

import pandas as pd
import pytest

from rateshock.config import SECTORS

ROOT = Path(__file__).resolve().parents[1]
T = ROOT / "results" / "tables"


@pytest.fixture(scope="module")
def primary():
    return pd.read_csv(T / "primary_betas.csv").set_index("ticker")


@pytest.fixture(scope="module")
def interaction():
    return pd.read_csv(T / "interaction_betas.csv").set_index("ticker")


@pytest.fixture(scope="module")
def inter_rob():
    df = pd.read_csv(T / "robustness_interaction.csv")
    return df[(df["sample"] == "baseline") & (df["window"] == "d0_p1")]


def test_market_response(primary):
    assert primary.loc["SPY", "beta"] == pytest.approx(-1.770, abs=0.02)
    assert primary.loc["SPY", "p"] == pytest.approx(0.031, abs=0.002)


def test_treasury_response_is_best_identified(primary):
    boot = pd.read_csv(T / "wild_bootstrap.csv").set_index("ticker")
    assert primary.loc["IEF", "beta"] == pytest.approx(-1.072, abs=0.02)
    assert primary.loc["IEF", "p"] < 0.002
    assert boot.loc["IEF", "wild_bootstrap_p"] < 0.006
    # IEF must remain the highest-R2 asset in the primary table
    assert primary["r2"].idxmax() == "IEF"


def test_no_equity_sector_is_significant(primary):
    """The central negative result. Must not silently become positive."""
    sec = primary.loc[[t for t in SECTORS]]
    assert (sec["p"] >= 0.05).all(), sec[sec["p"] < 0.05][["beta", "p"]]


def test_sector_ordering_is_stable(primary):
    sec = primary.loc[[t for t in SECTORS]].sort_values("beta")
    sensitive, defensive = list(sec.index[:3]), list(sec.index[-3:])
    assert "XLK" in sensitive and "XLY" in sensitive
    assert "XLP" in defensive and "XLE" in defensive


def test_pooled_cyclicals(primary):
    g = pd.read_csv(T / "pooled_group_tests.csv").set_index("name")
    assert g.loc["cyclicals", "beta"] == pytest.approx(-0.673, abs=0.02)
    assert g.loc["cyclicals", "p"] == pytest.approx(0.029, abs=0.002)


def test_no_robust_equity_inflation_interaction(interaction):
    """The second central negative result."""
    eq = interaction.loc[[t for t in SECTORS]]
    assert (eq["inter_p"] >= 0.05).all(), eq[eq["inter_p"] < 0.05]


def test_gold_interaction_is_threshold_robust(interaction, inter_rob):
    assert interaction.loc["GLD", "inter_beta"] > 0
    g = inter_rob[inter_rob["ticker"] == "GLD"]
    assert len(g) >= 5, "expected five inflation thresholds"
    assert (g["inter_beta"] > 0).all(), "gold interaction must not flip sign"


def test_xly_interaction_is_specification_sensitive(inter_rob):
    """XLY must NOT be promoted to a robust finding: it flips sign."""
    x = inter_rob[inter_rob["ticker"] == "XLY"]
    signs = set((x["inter_beta"] > 0).tolist())
    assert len(signs) == 2, (
        "XLY's interaction no longer flips sign across thresholds; the "
        "report's claim that it is specification-sensitive must be revisited")


def test_sample_and_identification_invariants():
    s = json.loads((T / "summary.json").read_text())
    assert s["n_events"] == 215
    assert s["all_dates_validated"] is True
    assert s["sample_end"] == "2023-12-13"
    assert s["corr_raw_vs_surprise"] == pytest.approx(0.467, abs=0.005)
    assert s["explained_variance"]["PC1"] < 0.30, "no dominant single factor"
    assert s["pca_dropped_assets"] == ["XLRE"]
