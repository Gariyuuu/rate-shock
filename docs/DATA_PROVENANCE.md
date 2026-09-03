# Data Provenance

Every series used in the study, where it came from, when it is published, what
was done to it, and what role it plays. All raw payloads are cached under
`data/raw/` so the pipeline is reproducible without re-hitting any source.

## Primary sources

| Series | Source | Frequency | Coverage used | Release timing | Transformation | Role |
|---|---|---|---|---|---|---|
| **Monetary policy surprise (MPS)** | Bauer & Swanson (2023), updated series published by the **Federal Reserve Bank of San Francisco** ([data page](https://www.frbsf.org/research-and-insights/data-and-indicators/monetary-policy-surprises/), `monetary-policy-surprises-data.xlsx`, sheet `FOMC (update 2023)`) | Per FOMC announcement | 1998-12-22 – 2023-12-13 (215 events in sample) | Measured in a 30-minute window bracketing the announcement | First principal component of 30-min changes in ED1–ED4 Eurodollar futures (SOFR SFR2–SFR5 from Jan 2023), scaled so the loading on the 4-quarter-ahead contract is 1. Converted from percentage points to **basis points** (×100). | **Primary explanatory variable** |
| **Orthogonalized surprise (MPS_ORTH)** | Same file | Per announcement | 202 in-sample events (NA by construction Mar–Dec 2020) | Same | Residual of MPS regressed on six pre-announcement macro/financial variables (Table 1 of Bauer–Swanson). ×100 to bp. | Co-primary shock; addresses Fed-information contamination |
| **30-min Treasury & S&P responses** | Same file (`TNOTE02`, `TNOTE10`, `TBOND`, `SP500 emini`) | Per announcement | Same | Same 30-min window | ×100 to bp | Independent validation of the **sign convention**; intraday benchmark. Never mixed with daily coefficients. |
| **FOMC announcement dates** | `federalreserve.gov` FOMC calendars (`fomccalendars.htm`, `fomchistorical{YYYY}.htm`) and the Board's monetary press-release archive | Per meeting | 1998–2024 | Statement released on the final meeting day | Statement/minutes URLs parsed for the embedded `YYYYMMDD`; unscheduled announcements verified by fetching the press release and reading its title | **Independent validation** of every event date |
| **Fed funds target** | FRED `DFEDTAR` (to 2008-12-15), `DFEDTARU` / `DFEDTARL` (corridor era) | Daily | 1998–2024 | Effective date, usually the business day **after** the announcement | Corridor summarised by its **midpoint**; change measured from the day before the announcement to up to 5 days after, capped at the day before the next announcement | `target_before`, `target_after`, `raw_change_bps` — the *non*-expectation-adjusted comparison |
| **Sector / benchmark / cross-asset prices** | Yahoo Finance via `yfinance` | Daily | 1998-01-01 – 2024-06-28 | Daily close, 16:00 ET | Split/dividend-adjusted close → daily **log returns in percent** | Dependent variables |
| **Headline CPI (NSA)** | FRED `CPIAUCNS` | Monthly | 1993– | Released ~2 weeks after the reference month | Year-over-year percent change | Inflation regime |
| **Core CPI (NSA)** | FRED `CPILFENS` | Monthly | 1993– | Same release | Year-over-year percent change | Regime sensitivity check |
| **CPI release dates** | **BLS news-release archive** (`bls.gov/bls/news-release/cpi.htm`) | Per release | 390 releases, ref. months 1994-01 – 2026-07 | The archive link text names the reference month; the URL encodes the exact release date | Parsed `(reference_month → release_date)` pairs; release time set to **08:30 ET** | **Release-date alignment** — the critical join |

## Asset inception dates (binding constraints)

| Asset | First observation | Consequence |
|---|---|---|
| 9 sector ETFs, SPY | 1998-12-22 | 213–214 usable events |
| QQQ | 1999-03-10 | 212 events |
| IEF, TLT | 2002-07-30 | 183 events |
| GLD | 2004-11-18 | 164 events |
| **XLRE** | **2015-10-08** | **only 72 events** — excluded from PCA/clustering, and its CIs are far wider than the other sectors' |
| BTC-USD | 2014-09-17 | Optional/exploratory only; 24/7 trading makes its daily bar non-comparable to a 09:30–16:00 ET session |

## The two joins that could silently corrupt the study

**1. CPI must be joined on release time, not calendar month.** CPI for month *M*
is published in the middle of month *M+1*. FOMC meetings routinely fall within
days of a CPI release. Merging on the meeting's calendar month would attach a
number published *weeks after* the meeting. We instead do a backward as-of merge
of `announcement_timestamp` against `release_timestamp`. Observed lag between a
release and the next FOMC announcement ranges from **0.23 to 34.24 days** — the
0.23-day cases are meetings where CPI printed at 08:30 ET the same morning the
statement landed at 14:00 ET, which correctly counts as known.

A convenient property: **NSA CPI is not revised**, so the YoY computed today
from `CPIAUCNS` for a given reference month equals the number the market saw.

**2. The target rate must be read at its effective date.** FRED stamps the
target at the date it takes effect, typically the business day *after* the
announcement. Reading the announcement-day level misses the move entirely for
meetings such as 2022-03-16. This was caught by a test asserting known target
changes and is now handled explicitly (see `src/rateshock/fomc.py`).

## Citation

> Bauer, Michael D., and Eric T. Swanson (2023). "A Reassessment of Monetary
> Policy Surprises and High-Frequency Identification." *NBER Macroeconomics
> Annual* 37, 87–155. Updated series published by the Federal Reserve Bank of
> San Francisco.

Supporting: Swanson & Jayawickrema (2024) for announcement timestamps; Bauer &
Chernov (2024) for the Treasury-skewness orthogonalization input.
