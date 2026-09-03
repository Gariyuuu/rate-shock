# Pre-Registered Hypotheses

**Written and committed before any regression was estimated.** The git history
for this file is the record. Nothing below was edited after results were seen;
where a prior turned out to be wrong, that is reported as a wrong prior in the
results section, not silently corrected here.

## Sign convention

`surprise_bps > 0` = **tighter-than-expected** policy: the futures-implied
policy path repriced *upward* in the 30-minute window around the announcement.

All betas are reported as **percentage-point change in return per +25bp
hawkish surprise**. A negative beta therefore means "falls when policy is
tighter than expected".

Baseline dependent variable: SPY-adjusted abnormal return, `AR = R_sector - R_SPY`,
over the `[0,+1]` trading-day window.

Because the baseline dependent variable is *benchmark-adjusted*, the priors
below are about **relative** performance versus the broad market, not about
direction in absolute terms. A hawkish surprise is expected to push essentially
every equity sector down in raw terms; the question here is which ones fall
*more* than the market.

## Directional priors

| # | Asset | Prior sign (AR vs SPY) | Economic reasoning |
|---|-------|------------------------|--------------------|
| H1 | **Financials (XLF)** | **Positive / weakly positive** | Banks earn a spread on rate-sensitive assets. A hawkish surprise steepens near-term policy expectations and raises reinvestment yields, supporting net interest margins. Offsetting forces (credit-quality fears, duration losses on securities portfolios) make the magnitude modest and the sign the least certain of the set. |
| H2 | **Technology (XLK)** | **Negative** | Long-duration cash flows. A higher discount rate mechanically compresses the present value of profits weighted far into the future, so tech should underperform the market on hawkish surprises. |
| H3 | **Utilities (XLU)** | **Negative** | Classic bond proxy: stable, bond-like cash flows and high leverage. Competes directly with Treasuries for yield-seeking capital, so it should fall as rates reprice upward. |
| H4 | **Real Estate (XLRE)** | **Negative, largest magnitude among equities** | Highest duration and highest leverage of the sectors; cap rates track long yields closely and financing costs pass through quickly. Expected to be the most rate-sensitive equity sector. |
| H5 | **Consumer Discretionary (XLY)** | **Negative** | Cyclical demand plus consumer credit sensitivity: tighter policy raises borrowing costs for big-ticket and financed purchases. |
| H6 | **Long Treasuries (TLT)** | **Negative, large magnitude** | Mechanical. Yields rise on a hawkish surprise, so a ~17-year-duration bond fund falls roughly in proportion to duration times the yield change. This is the strongest and most mechanical prior in the study; a failure here would indicate the surprise measure or the return alignment is broken. |

## Secondary priors

| # | Asset | Prior | Reasoning |
|---|-------|-------|-----------|
| H7 | Consumer Staples (XLP) | Positive vs SPY | Defensive, low beta; expected to outperform on a down move even though it is also somewhat bond-like. |
| H8 | Energy (XLE) | Ambiguous / near zero | Commodity-price driven; policy surprises affect it mainly through the dollar and growth expectations, which work in opposite directions. |
| H9 | IEF (7-10y Treasuries) | Negative, ~half the magnitude of TLT | Duration roughly 7-8y versus ~17y. |
| H10 | Gold (GLD) | Negative | Higher real rates raise the opportunity cost of holding a zero-coupon real asset. Weaker prior than TLT: the dollar and safe-haven channels can dominate. |

## Inflation-regime interaction

The central question. Two competing stories, stated in advance:

- **A. Amplification (interaction reinforces the main effect).** In a
  high-inflation regime, policy is the dominant macro risk factor. Investors
  read each surprise as information about a Fed that is behind or ahead of an
  inflation problem, so a given basis point of surprise moves more capital.
  Prediction: `beta_3` has the **same sign** as `beta_1`, i.e. rate-sensitive
  sectors become *more* rate-sensitive.
- **B. Attenuation.** In high-inflation regimes a hawkish surprise also signals
  Fed credibility and lower expected future inflation, partially offsetting the
  discount-rate channel. Prediction: `beta_3` has the **opposite sign** to
  `beta_1`.

**Stated prior: A (amplification), held with low confidence**, most clearly for
the long-duration sectors (XLK, XLRE, XLU). The 2021-2023 inflation episode
supplies most of the high-inflation observations, so this test is effectively
"was the 2022-2023 tightening cycle different", and it is confounded with that
period's other features. This is acknowledged in advance as a limitation, not a
discovery.

## Statistical-power caveat, stated in advance

There are on the order of 200 usable FOMC events, with a surprise standard
deviation of only a few basis points. Daily abnormal returns are noisy relative
to that signal. We therefore expect **wide confidence intervals and low R²**,
and we commit in advance to reporting insignificant results as insignificant
rather than reaching for a specification that produces stars.
