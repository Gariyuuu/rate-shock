"""The report must quote the numbers the pipeline actually produced.

This is the guard against a write-up drifting away from its results: every
headline figure below is read out of results/ and asserted to appear in
REPORT.md / README.md.
"""
import json
import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "results" / "tables"


@pytest.fixture(scope="module")
def report():
    return (ROOT / "REPORT.md").read_text()


@pytest.fixture(scope="module")
def readme():
    return (ROOT / "README.md").read_text()


@pytest.fixture(scope="module")
def primary():
    return pd.read_csv(TABLES / "primary_betas.csv").set_index("ticker")


@pytest.fixture(scope="module")
def summary():
    return json.loads((TABLES / "summary.json").read_text())


HEADLINE = ["SPY", "IEF", "TLT", "GLD", "XLK", "XLY", "XLU", "XLP", "XLF",
            "XLE", "XLV", "XLB", "XLI", "XLRE", "QQQ"]


def test_every_headline_beta_appears_in_report(report, primary):
    missing = []
    for tk in HEADLINE:
        b = primary.loc[tk, "beta"]
        # accept the sign-prefixed or bare rendering, 2dp, unicode minus too
        s = f"{abs(b):.2f}"
        if s not in report:
            missing.append((tk, b))
    assert not missing, f"betas absent from REPORT.md: {missing}"


def test_key_pvalues_match(report, primary):
    assert primary.loc["IEF", "p"] < 0.005
    assert "0.001" in report
    assert primary.loc["SPY", "p"] == pytest.approx(0.031, abs=0.0005)
    assert "0.031" in report


def test_no_sector_is_claimed_significant_when_it_is_not(primary):
    """The report's central claim: no individual SECTOR beta is significant."""
    from rateshock.config import SECTORS
    sectors = primary.loc[[t for t in SECTORS if t in primary.index]]
    assert (sectors["p"] >= 0.05).all(), (
        "a sector became significant; REPORT.md section 5.1 must be rewritten: "
        f"{sectors[sectors['p'] < 0.05][['beta', 'p']].to_dict()}")


def test_event_counts_match(report, readme, summary):
    n = summary["n_events"]
    assert n == 215
    assert str(n) in report and str(n) in readme
    assert summary["all_dates_validated"] is True


def test_surprise_correlation_claim(report, summary):
    corr = summary["corr_raw_vs_surprise"]
    assert f"{corr:.3f}" in report, f"corr {corr:.3f} not quoted"
    assert corr < 0.75


def test_robustness_counts_quoted(report, readme):
    rob = pd.read_csv(TABLES / "robustness_all.csv")
    inter = pd.read_csv(TABLES / "robustness_interaction.csv")
    assert f"{len(rob):,}" in report or str(len(rob)) in report
    assert str(len(inter)) in report
    assert f"{len(rob):,}" in readme or str(len(rob)) in readme


def test_pca_variance_quoted(report, summary):
    pc1 = summary["explained_variance"]["PC1"] * 100
    assert f"{pc1:.1f}" in report, f"PC1 {pc1:.1f}% not quoted"


def test_clusters_quoted(report, summary):
    for members in summary["clusters"].values():
        for tk in members:
            assert tk in report


def test_all_required_figures_exist_and_are_referenced(report, readme):
    figs = sorted((ROOT / "results" / "figures").glob("*.png"))
    assert len(figs) == 10, [f.name for f in figs]
    for f in figs:
        assert f.stat().st_size > 10_000, f"{f.name} looks empty"
        assert f.name in readme, f"{f.name} not linked from README"


def test_hypotheses_were_committed_before_results():
    """Pre-registration must exist and state the sign convention."""
    h = (ROOT / "docs" / "HYPOTHESES.md").read_text()
    assert "tighter-than-expected" in h
    for tag in ("H1", "H2", "H3", "H4", "H5", "H6"):
        assert tag in h
    assert "amplification" in h.lower()


def test_provenance_documents_every_source():
    p = (ROOT / "docs" / "DATA_PROVENANCE.md").read_text()
    for src in ("Bauer", "Swanson", "FRED", "BLS", "DFEDTARU", "CPIAUCNS",
                "federalreserve.gov", "yfinance"):
        assert src in p, f"{src} missing from provenance"


def test_no_unsupported_causal_language(report):
    """Guard against causal overreach in the write-up."""
    banned = [r"\bproves\b", r"\bproven\b", r"causes the\b",
              r"\bdemonstrates that .{0,40}\bcauses\b"]
    for pat in banned:
        assert not re.search(pat, report, re.I), f"causal overreach: {pat}"
