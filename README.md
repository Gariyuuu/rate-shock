# Rate Shock

**Which assets react most strongly when the Federal Reserve surprises the market?**

An event study of 215 FOMC announcements from December 1998 to December 2023.
The explanatory variable is not the change in the fed funds target but the
**expectation-adjusted policy surprise** — the Bauer & Swanson (2023) measure,
built from 30-minute moves in Eurodollar and SOFR futures around each
announcement, as published by the Federal Reserve Bank of San Francisco. Sector
responses are measured as SPY-adjusted abnormal returns over a [0,+1]
trading-day window; Treasuries and gold enter on a raw-return basis. The
question is which parts of the market flinch, by how much, and whether that
changes when inflation is high.

![Sector monetary-policy sensitivity, with 95% confidence intervals](results/figures/03_sector_beta_forest.png)

## What I found

- **Broad equity prices fall after hawkish policy surprises.** A +25bp
  tighter-than-expected surprise moves SPY by **−1.77%** (95% CI [−3.38, −0.16],
  p = 0.031).
- **Treasury exposure gives the clearest response in the sample.** IEF returns
  **−1.07%** per +25bp (p = 0.001, wild-bootstrap p = 0.003) and is the
  best-identified coefficient in the study.
- **Sector-level effects are far less stable than the broad-market effect.** The
  ordering is economically sensible — Technology (−1.32) and Consumer
  Discretionary (−0.95) at the sensitive end, Consumer Staples (+1.13) and
  Energy (+1.06) at the defensive end — but **no individual equity sector is
  significant at the 5% level** (smallest p = 0.053). Only a pooled test of
  cyclicals clears it: **−0.67%, p = 0.029**.
- **Inflation-regime amplification is not robust for equities.** Every
  sector-level interaction between the surprise and a high-inflation dummy is
  insignificant.
- **Gold shows the most robust regime interaction observed.** Its response to
  hawkish surprises is strongly negative in low-inflation regimes and roughly
  zero in high-inflation ones, and that interaction keeps its sign and rough
  magnitude across all five inflation thresholds tested.
- **Longer event windows materially reduce identification strength.** For an
  identical shock and asset, R² falls from 0.25 in a 30-minute window to 0.09
  over two days.

Full write-up with tables, diagnostics and figures: **[report/REPORT.md](report/REPORT.md)**.

## The identification point

**A realized target-rate change is not a monetary-policy surprise.** Markets
price expectations; only the unexpected component should move valuations.

This is not a technicality in this sample. Of the 215 announcements,
**144 involved no change in the fed funds target at all** — yet those meetings
still carry surprises with a standard deviation of 4.0bp and a maximum absolute
surprise of 15.2bp, because the FOMC moved expectations through guidance rather
than through the current-period rate. Across the whole sample the realized
target change and the measured surprise correlate only **0.467**.

A design keyed on the realized change would therefore discard most of the usable
variation and mismeasure the rest. Raw target changes are reported here only as
an explicitly labelled exploratory contrast, and are **never** substituted for
the surprise.

## Implementation lessons

Three research-engineering issues that materially changed the results or the
workflow, kept here because each is the kind of thing that silently corrupts an
event study:

**FRED effective dates.** FRED records the fed funds target by the date it takes
*effect*, which is usually the business day after the announcement. Reading the
announcement-day level therefore misses the move entirely for meetings such as
2022-03-16. Caught by a test asserting known target changes; the pipeline now
measures the change over a forward window capped at the next announcement.

**Cross-asset benchmarks.** Subtracting an equity benchmark from a Treasury
return is not an abnormal return — it injects equity noise into a bond response
and answers a question nobody asked. TLT's SPY-adjusted beta is **+0.15**; its
correct raw beta is **−1.31**. The return basis is now a property of the asset
class, set in `config.default_dep` and enforced by tests.

**Negative caching of failed requests.** Confirming unscheduled announcements
requires probing the a/b/c suffixes of Fed press-release URLs, most of which
404. Until those failures were cached alongside successes, every pipeline run
re-issued them and took minutes instead of seconds.

## Limitations

Stated plainly, because they bound what the study can claim:

- The **surprise dataset ends 2023-12-13**, the limit of the published
  Bauer–Swanson update. Nothing here speaks to policy after that date.
- **High-frequency analysis is limited to the 30-minute event measurements**
  that ship with the Bauer–Swanson dataset. **No sector-level intraday data was
  available**, so the wider intraday windows this design would ideally use could
  not be constructed.
- **Longer windows admit substantially more unrelated market news.** Wider
  windows produce larger point estimates but weaker identification; they are
  reported, not preferred.
- **Statistical power is the binding constraint.** 215 events with a 5.9bp
  surprise standard deviation leaves sector confidence intervals ±2–3
  percentage points wide. The FOMC meets eight times a year; no econometric
  choice relaxes this.
- **XLRE has only ~72 usable events** (it launched in October 2015), is unstable
  under every perturbation, and is excluded from the PCA and clustering. Its
  estimates should not be used.
- **Many sector coefficients are specification-sensitive.** Seven of ten change
  sign somewhere in the robustness battery (Utilities spans −2.44 to +1.96).
  Only IEF, TLT, GLD, QQQ, XLB, XLI and XLV hold their sign throughout. The
  instability is concentrated: under the six exclusion-type filters only
  Utilities, Energy and Real Estate flip, but splitting the sample pre/post-2008
  additionally flips Technology, Consumer Discretionary, Staples, Financials
  and SPY itself — the zero-lower-bound era is a different monetary regime.
- **These are event-study associations, not structural causal estimates.** The
  design identifies price responses to policy news in a 1–2 day window. It says
  nothing about the real economy, longer-horizon returns, or sector
  fundamentals.

Three of six pre-registered directional priors — Financials, Utilities and Real
Estate — came out with the **wrong sign**. They were not rewritten; §5.3 of the
report discusses why benchmark-adjusted returns confound duration with market
beta.

## Reproducing

```bash
python3.11 -m venv .venv
./.venv/bin/pip install -r requirements.txt

./.venv/bin/python scripts/run_analysis.py   # main reproduction entrypoint
./.venv/bin/python -m pytest tests/ -q       # 70 tests
```

`scripts/run_analysis.py` is the single entrypoint: it fetches (or reads cached)
data, builds the event database, runs every regression, and writes all tables
and figures under `results/`. There is no notebook state and no manual step.
Wiping `results/`, `data/interim/` and `data/processed/` and re-running
regenerates all 19 CSV/JSON artifacts **byte-for-byte identically**.

Raw downloads are cached under `data/raw/` (not committed — see
[`data/README.md`](data/README.md)), so a second run is offline and takes about
40 seconds.

### Pre-registration

Hypotheses were committed **before** the primary results were generated, and the
original file remains unchanged. `git log docs/HYPOTHESES.md` shows the
pre-registration commit preceding the result-generating commit.

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
scripts/run_analysis.py   main reproduction entrypoint
docs/HYPOTHESES.md        pre-registered, committed before estimation
docs/DATA_PROVENANCE.md   every source, frequency, release timing, transform
data/README.md            what is cached, what is committed, how to refetch
report/REPORT.md          full empirical write-up
site/                     static presentation page (deployed)
results/tables/           12 CSVs + summary.json
results/figures/          10 PNGs
tests/                    70 tests
```

## Method

- **Sample**: 215 FOMC announcements, 1998-12-22 → 2023-12-13, 15 unscheduled.
  **Every date validated** against the Federal Reserve's own announcement
  history (207 by statement URL, 5 by minutes, 3 unscheduled confirmed by
  press-release title). Zero unvalidated.
- **Sign convention**: `surprise_bps > 0` = **tighter than expected**. Verified,
  not assumed — the 30-minute 10-year yield response loads +0.44 (t = 7.0) on
  the surprise.
- **Windows**: [−5,+5], [−1,+1], **[0,+1]** (pre-registered baseline), [0,+5].
  Daily and intraday estimates are reported as separate coefficients, never
  mixed.
- **Abnormal return**: `AR = R_sector − R_SPY` for sectors; raw returns for
  SPY, IEF, TLT and GLD.
- **Inflation regime**: latest **released** CPI at each announcement, joined by
  an as-of merge on timestamps against 390 real BLS release dates, so no
  post-announcement CPI can leak into the regime flag.
- **Inference**: HC1 robust standard errors; HC0/HC3 and a Rademacher wild
  bootstrap in the robustness battery. Betas reported per +25bp.
- **Robustness**: **2,886 primary + 465 interaction estimates persisted** across
  8 sample filters × 4 windows × 2 shock measures × 3 return definitions × 5
  inflation thresholds. Nothing was run and discarded.

## Figures

| | |
|---|---|
| 1 | [FOMC event timeline](results/figures/01_event_timeline.png) |
| 2 | [Surprise distribution and surprise vs raw change](results/figures/02_surprise_distribution.png) |
| 3 | [**Sector beta forest plot**](results/figures/03_sector_beta_forest.png) |
| 4 | [Event-time CAR curves](results/figures/04_car_curves.png) |
| 5 | [High vs low inflation sector betas](results/figures/05_regime_betas.png) |
| 6 | [Asset × event response heatmap](results/figures/06_response_heatmap.png) |
| 7 | [Treasury vs equity response scatter](results/figures/07_treasury_equity_scatter.png) |
| 8 | [PCA projection](results/figures/08_pca_projection.png) |
| 9 | [Clustering dendrogram](results/figures/09_dendrogram.png) |
| 10 | [Robustness coefficient plot](results/figures/10_robustness.png) |

## Data sources

Bauer & Swanson (2023) monetary policy surprises via the **Federal Reserve Bank
of San Francisco**; FOMC announcement history via **federalreserve.gov**; fed
funds target via **FRED** (`DFEDTAR`, `DFEDTARU`, `DFEDTARL`); CPI via **FRED**
(`CPIAUCNS`, `CPILFENS`) with release dates scraped from the **BLS**
news-release archive; prices via **Yahoo Finance**. Full table:
[`docs/DATA_PROVENANCE.md`](docs/DATA_PROVENANCE.md).

> Bauer, Michael D., and Eric T. Swanson (2023). "A Reassessment of Monetary
> Policy Surprises and High-Frequency Identification." *NBER Macroeconomics
> Annual* 37, 87–155.

## Frozen scope

This study is complete and its scope is frozen. `tests/test_frozen_results.py`
pins the headline estimates so a future refactor cannot silently move a
conclusion. Extensions — more sectors, other event windows, additional macro
indicators, trading strategies — belong in a separate project, not here.
