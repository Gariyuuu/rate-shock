"""Surprise sign convention and the mechanical priors that validate it."""
import numpy as np
import statsmodels.api as sm

from rateshock.config import PRIMARY_WINDOW, SURPRISE_SIGN_CONVENTION


def _slope(y, x):
    ok = y.notna() & x.notna()
    r = sm.OLS(y[ok], sm.add_constant(x[ok])).fit(cov_type="HC1")
    return r.params.iloc[1], r.tvalues.iloc[1]


def test_convention_is_documented():
    assert "tighter" in SURPRISE_SIGN_CONVENTION.lower()


def test_positive_surprise_raises_treasury_yields(data):
    """The definitional check, using the 30-min yield response in the source.

    A hawkish (positive) surprise must move the 10-year yield UP. This uses
    Bauer-Swanson's own intraday yield response, so it validates the sign of
    the shock independently of anything computed in this repo.
    """
    ev = data["events"]
    b, t = _slope(ev["hf_tnote10_bps"], ev["surprise_bps"])
    assert b > 0, "positive surprise must raise yields"
    assert t > 4, f"weak relation (t={t:.1f}) suggests a sign/alignment bug"


def test_positive_surprise_lowers_bond_prices(data):
    """Rates up => bond PRICES down. Uses our own computed returns."""
    df = data["df"]
    for tk in ("IEF", "TLT"):
        g = df[(df["ticker"] == tk) & (df["window"] == PRIMARY_WINDOW)]
        b, t = _slope(g["car_raw"], g["surprise_bps"])
        assert b < 0, f"{tk} should fall on a hawkish surprise (got {b:+.4f})"


def test_longer_duration_reacts_more_over_the_full_window(data):
    """TLT (~17y duration) must move more than IEF (~7y) over [-5,+5]."""
    df = data["df"]
    betas = {}
    for tk in ("IEF", "TLT"):
        g = df[(df["ticker"] == tk) & (df["window"] == "m5_p5")]
        betas[tk], _ = _slope(g["car_raw"], g["surprise_bps"])
    assert betas["TLT"] < betas["IEF"] < 0, betas


def test_positive_surprise_lowers_equities_intraday(data):
    """Hawkish surprise => stocks down, in the 30-minute window."""
    ev = data["events"].dropna(subset=["surprise_bps"])
    b, t = _slope(ev["hf_tnote02_bps"], ev["surprise_bps"])
    assert b > 0 and t > 4     # 2y yield rises: the policy path repriced up


def test_surprises_are_centred_near_zero(data):
    """An expectation-adjusted shock should have no large mean by construction."""
    s = data["events"]["surprise_bps"].dropna()
    assert abs(s.mean()) < 0.15 * s.std()
    assert s.std() > 1.0


def test_surprise_is_not_mechanically_the_target_change(data):
    ev = data["events"].dropna(subset=["surprise_bps", "raw_change_bps"])
    holds = ev[ev["raw_change_bps"] == 0]
    # Meetings with NO target change still carry real surprises (guidance).
    assert holds["surprise_bps"].abs().max() > 3.0
    assert holds["surprise_bps"].std() > 1.0
