# rate-shock

**How do unexpected Federal Reserve policy announcements affect U.S. equity
sectors, and does that sensitivity change between high- and low-inflation
regimes?**

An event-study / econometrics project on 215 FOMC announcements, 1998–2023.

![Sector monetary-policy sensitivity](results/figures/03_sector_beta_forest.png)

---

## Headline results

| | |
|---|---|
| **Market response** | **−1.77%** per +25bp hawkish surprise (SPY, 95% CI [−3.38, −0.16], p = 0.031) |
| **Best-identified asset** | **IEF** −1.07% (p = 0.001, bootstrap p = 0.003, R² = 0.080) |
| **Most rate-sensitive sectors** | Technology (−1.32), Consumer Discretionary (−0.95), Materials (−0.78) |
| **Most defensive sectors** | Consumer Staples (+1.13), Energy (+1.06), Utilities (+0.63) |
| **Individually significant sectors** | **None at the 5% level.** Pooled cyclicals: −0.67, p = 0.029 |
| **Inflation-regime interaction** | **Not supported for equities.** 13 of 15 interactions p > 0.25 |
| **Only threshold-robust regime effect** | **Gold** stops responding to surprises when inflation is high (β₃ = +4.19, stable across all five thresholds) |

Read the full write-up in **[REPORT.md](REPORT.md)**.

## What makes this an identification study rather than a dashboard

**A rate change is not a rate surprise.** 144 of the 215 announcements involved
*no change* in the fed funds target, yet those meetings still carry surprises
with a 4.0bp standard deviation — the FOMC moved expectations through guidance.
The correlation between the realized target change and the actual surprise is
only **0.467**.

The primary regressor is therefore the **Bauer & Swanson (2023)** high-frequency
surprise (updated series published by the Federal Reserve Bank of San
Francisco): the first principal component of 30-minute changes in ED1–ED4
Eurodollar futures — SOFR futures from 2023 — around each announcement. Raw
target changes are reported only as an explicitly labelled contrast and are
**never** substituted for the surprise.

Three design details that decide whether the study is sound:

1. **CPI is joined on its true release date.** CPI for month *M* prints in the
   middle of month *M+1*, and FOMC meetings routinely fall within days of a
   release. We scrape 390 observed `(reference month → release date)` pairs from
   the BLS news-release archive and do a backward as-of merge on *timestamps*
   (CPI at 08:30 ET, FOMC at 14:00 ET), so a same-morning CPI print correctly
   counts as known. Observed lags run from 0.23 to 34.24 days.
2. **Cross-assets use raw returns.** Subtracting an equity benchmark from a bond
   return is not an abnormal return. TLT's SPY-adjusted beta is +0.15; its
   correct raw beta is −1.31. Enforced in `config.default_dep`, and tested.
3. **The target rate is read at its effective date.** FRED stamps the target
   when it takes effect — usually the day *after* the announcement — so reading
   the announcement-day level misses the move entirely (e.g. 2022-03-16). Caught
   by a test, then fixed.

## Reproducing

```bash
git clone <this repo> && cd rate-shock
python3.11 -m venv .venv
./.venv/bin/pip install -r requirements.txt

./.venv/bin/python scripts/run_analysis.py   # full pipeline: data -> tables -> figures
./.venv/bin/python -m pytest tests/ -q       # 61 tests
```

Raw downloads are cached under `data/raw/`, so a second run is offline and
takes seconds. Delete that directory to re-fetch from source.

## Layout

```
src/rateshock/
  config.py       tickers, windows, thresholds, sign convention, return basis
  http_util.py    cached + negative-cached HTTP
  fomc.py         surprise ingest, official date validation, target changes
  cpi.py          BLS release-date scrape, release-time-aligned regime
  prices.py       ETF price data + coverage checks
  events.py       trading-day mapping, event windows, abnormal returns
  regressions.py  primary betas, interactions, pooled tests
  crossasset.py   response matrix, correlations
  cluster.py      PCA, hierarchical clustering
  robustness.py   sample filters, wild bootstrap, full battery
  figures.py      all ten figures
scripts/run_analysis.py
docs/HYPOTHESES.md          pre-registered, committed before estimation
docs/DATA_PROVENANCE.md     every source, frequency, release timing, transform
results/tables/             12 CSVs + summary.json
results/figures/            10 PNGs
```

## Figures

| | |
|---|---|
| 1 | [FOMC event timeline](results/figures/01_event_timeline.png) |
| 2 | [Surprise distribution + surprise vs raw change](results/figures/02_surprise_distribution.png) |
| 3 | [**Sector beta forest plot (hero)**](results/figures/03_sector_beta_forest.png) |
| 4 | [Event-time CAR curves](results/figures/04_car_curves.png) |
| 5 | [High vs low inflation sector betas](results/figures/05_regime_betas.png) |
| 6 | [Asset × event response heatmap](results/figures/06_response_heatmap.png) |
| 7 | [Treasury vs equity response scatter](results/figures/07_treasury_equity_scatter.png) |
| 8 | [PCA projection](results/figures/08_pca_projection.png) |
| 9 | [Clustering dendrogram](results/figures/09_dendrogram.png) |
| 10 | [Robustness coefficient plot](results/figures/10_robustness.png) |

## Method

- **Sample**: 215 FOMC announcements, 1998-12-22 → 2023-12-13, 15 unscheduled.
  **Every date validated** against the Fed's own announcement history (207 by
  statement URL, 5 by minutes, 3 unscheduled confirmed by press-release title).
  Zero unvalidated.
- **Sign convention**: `surprise_bps > 0` = **tighter than expected**. Verified,
  not assumed: the 30-min 10y yield response loads +0.44 (t = 7.0) on the
  surprise.
- **Windows**: [−5,+5], [−1,+1], **[0,+1]** (pre-registered baseline), [0,+5].
  Daily and intraday estimates are reported in separate coefficients, never
  mixed.
- **Abnormal return**: `AR = R_sector − R_SPY` for sectors; raw returns for
  SPY/IEF/TLT/GLD.
- **Inference**: HC1 robust SEs; HC0/HC3 and a Rademacher wild bootstrap in the
  robustness battery. Betas reported per +25bp.
- **Robustness**: **2,886 primary + 465 interaction estimates persisted** across
  8 sample filters × 4 windows × 2 shock measures × 3 return definitions × 5
  inflation thresholds. Nothing run and discarded.

## Honest limitations

- **Power is the binding constraint.** With 215 events and a 5.9bp surprise SD,
  sector CIs are ±2–3pp wide. Moving from a 30-minute to a two-day window drops
  R² from 0.25 to 0.09 for the same shock and asset. The FOMC meets eight times
  a year; no econometric choice fixes this.
- **About half the sector betas are not sign-stable** across sample
  perturbations (XLU spans −2.44 to +1.96). Only IEF, TLT, GLD, XLK, QQQ, XLY,
  XLB and XLI hold their sign throughout.
- **XLRE should not be used**: 72 events, all post-2015, unstable everywhere,
  excluded from PCA/clustering.
- **3 of 6 pre-registered directional priors were wrong** (Financials,
  Utilities, Real Estate). The hypotheses were not rewritten; §5.3 of the report
  discusses why benchmark-adjusted returns confound duration with market beta.
- **Sample ends 2023-12-13** — the limit of the published surprise series.
- The design identifies price responses in a 1–2 day announcement window. It
  makes **no causal claim** about the real economy, longer-horizon returns, or
  sector fundamentals.

## Data sources

Bauer & Swanson (2023) monetary policy surprises via the **Federal Reserve Bank
of San Francisco**; FOMC announcement history via **federalreserve.gov**; fed
funds target via **FRED** (`DFEDTAR`, `DFEDTARU`, `DFEDTARL`); CPI via **FRED**
(`CPIAUCNS`, `CPILFENS`) with release dates from the **BLS** news-release
archive; prices via **Yahoo Finance**. Full table with frequencies, release
timing, transformations and roles: [`docs/DATA_PROVENANCE.md`](docs/DATA_PROVENANCE.md).

> Bauer, Michael D., and Eric T. Swanson (2023). "A Reassessment of Monetary
> Policy Surprises and High-Frequency Identification." *NBER Macroeconomics
> Annual* 37, 87–155.
