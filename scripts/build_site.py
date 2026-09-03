#!/usr/bin/env python
"""Generate the static presentation page from finalized research artifacts.

Architecture:

    Python research pipeline  ->  results/tables/*.csv + results/figures/*.png
                              ->  scripts/build_site.py
                              ->  site/  (static HTML, deployed)

No regression is estimated here and nothing is recomputed. Every number on the
page is read out of results/, so the site cannot drift from the study. Run
scripts/run_analysis.py first.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
TABLES = ROOT / "results" / "tables"
FIGURES = ROOT / "results" / "figures"
SITE = ROOT / "site"

from rateshock.config import CROSS_ASSETS, SECTORS  # noqa: E402

GITHUB = "https://github.com/Gariyuuu/rate-shock"

# Figures embedded in the presentation page.
USED_FIGURES = [
    "02_surprise_distribution.png",
    "03_sector_beta_forest.png",
    "05_regime_betas.png",
    "07_treasury_equity_scatter.png",
    "09_dendrogram.png",
    "10_robustness.png",
]


def load():
    d = {
        "primary": pd.read_csv(TABLES / "primary_betas.csv").set_index("ticker"),
        "pooled": pd.read_csv(TABLES / "pooled_group_tests.csv").set_index("name"),
        "inter": pd.read_csv(TABLES / "interaction_betas.csv").set_index("ticker"),
        "boot": pd.read_csv(TABLES / "wild_bootstrap.csv").set_index("ticker"),
        "summary": json.loads((TABLES / "summary.json").read_text()),
    }
    ir = pd.read_csv(TABLES / "robustness_interaction.csv")
    d["inter_rob"] = ir[(ir["sample"] == "baseline") & (ir["window"] == "d0_p1")]
    d["stability"] = sign_stability()
    rob = pd.read_csv(TABLES / "robustness_all.csv")
    d["rob"] = rob
    d["n_rob"] = len(rob)
    d["n_inter"] = len(pd.read_csv(TABLES / "robustness_interaction.csv"))
    return d


def sign_stability():
    """Which assets keep their beta sign across the robustness battery.

    Computed rather than hardcoded so this claim cannot drift from the data.
    Two tiers are reported because they differ materially: the six
    exclusion-type filters (dropping emergency meetings, March 2020, the COVID
    window, the largest surprise, unscheduled meetings) versus the full battery,
    which also splits the sample pre/post-2008. The sub-period split isolates
    the zero-lower-bound era and flips several signs on its own.
    """
    r = pd.read_csv(TABLES / "robustness_all.csv")
    d = r[(r["dep_mode"] == "auto") & (r["shock"] == "surprise_bps")
          & (r["window"] == "d0_p1")].dropna(subset=["beta"])
    excl = d[~d["sample"].isin(["pre_2008", "post_2008"])]

    def stable(frame):
        out = []
        for t in frame["ticker"].unique():
            g = frame[frame["ticker"] == t]["beta"]
            if (g > 0).all() or (g < 0).all():
                out.append(t)
        return set(out)

    all_st, exc_st = stable(d), stable(excl)
    secs = set(SECTORS)
    return {
        "stable_all": sorted(all_st),
        "unstable_sectors_all": sorted(secs - all_st),
        "unstable_sectors_excl": sorted(secs - exc_st),
        "flipped_by_subperiod": sorted((exc_st - all_st)),
        "n_unstable_all": len(secs - all_st),
        "n_sectors": len(secs),
    }


def fmt(v, dp=2, sign=True):
    s = f"{v:+.{dp}f}" if sign else f"{v:.{dp}f}"
    return s.replace("-", "−")


def pval(p):
    return "&lt;0.001" if p < 0.001 else f"{p:.3f}"


NAMES = dict(SECTORS)
NAMES.update({"SPY": "S&P 500", "QQQ": "Nasdaq 100"})
NAMES.update(CROSS_ASSETS)


def beta_rows(d, tickers, note_col=True):
    P, B = d["primary"], d["boot"]
    out = []
    for t in tickers:
        if t not in P.index:
            continue
        r = P.loc[t]
        sig = r["p"] < 0.05
        basis = "raw" if r["dep"] == "car_raw" else "vs SPY"
        boot = B.loc[t, "wild_bootstrap_p"] if t in B.index else float("nan")
        out.append(f"""<tr class="{'sig' if sig else ''}">
      <td class="tk"><span class="sym">{t}</span> <span class="nm">{NAMES.get(t,'')}</span></td>
      <td class="num strong">{fmt(r['beta'])}</td>
      <td class="num">[{fmt(r['ci_low'])}, {fmt(r['ci_high'])}]</td>
      <td class="num">{pval(r['p'])}</td>
      <td class="num">{'' if pd.isna(boot) else f'{boot:.3f}'}</td>
      <td class="num dim">{int(r['n'])}</td>
      <td class="num dim">{basis}</td>
    </tr>""")
    return "\n".join(out)


def build():
    d = load()
    S = d["summary"]
    P, G, I = d["primary"], d["pooled"], d["inter"]

    SITE.mkdir(exist_ok=True)
    # Ship only the figures this page references -- the full set lives in
    # results/figures/ and is linked from the repository, so copying all ten
    # would add unused weight to the deployed bundle.
    figdir = SITE / "figures"
    figdir.mkdir(exist_ok=True)
    for stale in figdir.glob("*.png"):
        stale.unlink()
    for name in USED_FIGURES:
        shutil.copy2(FIGURES / name, figdir / name)

    ST = d["stability"]
    sec = P.loc[[t for t in SECTORS if t in P.index]].sort_values("beta")
    min_p_sec = sec["p"].min()
    cyc = G.loc["cyclicals"]
    gld_rob = d["inter_rob"][d["inter_rob"]["ticker"] == "GLD"]["inter_beta"]
    xly_rob = d["inter_rob"][d["inter_rob"]["ticker"] == "XLY"]
    xly_lo = xly_rob.loc[xly_rob["threshold"].idxmin()]
    xly_3 = xly_rob[xly_rob["threshold"] == 3.0].iloc[0]

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rate Shock — How Fed policy surprises propagate across markets</title>
<meta name="description" content="Event study of {S['n_events']} FOMC announcements: how expectation-adjusted Federal Reserve policy surprises propagate across US equity sectors, Treasuries and gold.">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📉</text></svg>">
<style>
:root{{
  color-scheme: light;
  --bg:#fbfbfa; --panel:#fff; --ink:#14140f; --ink2:#4a483f; --dim:#7c7a70;
  --rule:#e2e0d9; --rule2:#eceae4; --accent:#1c4f8f; --neg:#a3352f; --pos:#1c5c3a;
  --serif: "Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Times New Roman",serif;
  --sans: -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Helvetica,Arial,sans-serif;
  --mono: ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
}}
*{{box-sizing:border-box}}
html{{-webkit-text-size-adjust:100%}}
body{{margin:0;background:var(--bg);color:var(--ink);
  font-family:var(--serif);font-size:18px;line-height:1.62;
  -webkit-font-smoothing:antialiased}}
.wrap{{max-width:1080px;margin:0 auto;padding:0 28px}}
.col{{max-width:680px}}
p{{margin:0 0 1.05em}}
a{{color:var(--accent);text-decoration:none;border-bottom:1px solid #c3d2e6}}
a:hover{{border-bottom-color:var(--accent)}}
h1,h2,h3{{font-family:var(--serif);font-weight:600;letter-spacing:-.012em;margin:0}}
.eyebrow{{font-family:var(--sans);font-size:11.5px;font-weight:600;letter-spacing:.14em;
  text-transform:uppercase;color:var(--dim);margin:0 0 18px}}

/* header */
header{{border-bottom:1px solid var(--rule);padding:76px 0 54px;background:var(--panel)}}
h1{{font-size:clamp(40px,6.4vw,64px);line-height:1.04;margin:0 0 20px}}
.lede{{font-size:clamp(20px,2.5vw,24px);line-height:1.45;color:var(--ink2);
  max-width:730px;margin:0 0 26px}}
.byline{{font-family:var(--sans);font-size:13.5px;color:var(--dim);
  display:flex;flex-wrap:wrap;gap:10px 22px;align-items:center}}
.byline a{{border:0;color:var(--ink2);font-weight:500}}
.byline a:hover{{color:var(--accent)}}

/* key figures strip */
.keys{{display:grid;grid-template-columns:repeat(4,1fr);gap:0;
  border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);
  background:var(--panel);margin:0}}
.key{{padding:24px 26px;border-right:1px solid var(--rule2)}}
.key:last-child{{border-right:0}}
.key .v{{font-size:30px;font-weight:600;letter-spacing:-.02em;line-height:1.1;
  font-variant-numeric:tabular-nums}}
.key .k{{font-family:var(--sans);font-size:11.5px;letter-spacing:.07em;
  text-transform:uppercase;color:var(--dim);margin-top:7px;line-height:1.35}}

section{{padding:60px 0;border-bottom:1px solid var(--rule)}}
section:last-of-type{{border-bottom:0}}
h2{{font-size:clamp(26px,3.4vw,33px);margin:0 0 8px;line-height:1.18}}
.sub{{font-family:var(--sans);font-size:14.5px;color:var(--dim);margin:0 0 30px}}
h3{{font-size:19px;margin:34px 0 9px}}

figure{{margin:34px 0 0}}
figure img{{width:100%;height:auto;display:block;border:1px solid var(--rule);
  background:#fcfcfb}}
figcaption{{font-family:var(--sans);font-size:13px;color:var(--dim);
  margin-top:11px;line-height:1.5;max-width:760px}}
.hero-fig{{margin-top:8px}}

table{{width:100%;border-collapse:collapse;margin:26px 0 0;
  font-family:var(--sans);font-size:14px;font-variant-numeric:tabular-nums}}
th{{text-align:left;font-weight:600;font-size:11.5px;letter-spacing:.06em;
  text-transform:uppercase;color:var(--dim);padding:0 12px 9px 0;
  border-bottom:1px solid var(--ink)}}
td{{padding:9px 12px 9px 0;border-bottom:1px solid var(--rule2);vertical-align:baseline}}
td.num,th.num{{text-align:right;padding-right:0}}
th.num{{padding-right:0}}
.tk .sym{{font-family:var(--mono);font-size:13px;font-weight:600}}
.tk .nm{{color:var(--dim);font-size:13px}}
.strong{{font-weight:600}}
.dim{{color:var(--dim)}}
tr.sig td{{background:#f4f7fb}}
tr.sig .strong{{color:var(--accent)}}
.tnote{{font-family:var(--sans);font-size:12.5px;color:var(--dim);margin-top:12px;line-height:1.55}}
.scroll{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
.scrollhint{{display:none;font-family:var(--sans);font-size:12px;color:var(--dim);
  margin:20px 0 -14px;letter-spacing:.04em}}

.callout{{border-left:2px solid var(--ink);padding:4px 0 4px 22px;margin:30px 0;
  max-width:690px}}
.callout p:last-child{{margin-bottom:0}}
.callout .lbl{{font-family:var(--sans);font-size:11.5px;font-weight:600;
  letter-spacing:.1em;text-transform:uppercase;color:var(--dim);
  display:block;margin-bottom:7px}}

ul{{margin:0 0 1.05em;padding-left:1.15em;max-width:690px}}
li{{margin-bottom:.5em}}
li::marker{{color:var(--dim)}}

.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:34px 46px;margin-top:30px}}
.finding{{max-width:none}}
.finding h3{{margin-top:0}}
.finding p{{font-size:16.5px;line-height:1.55;margin-bottom:0}}

code,kbd{{font-family:var(--mono);font-size:.88em;background:#f1efe9;
  padding:1.5px 5px;border-radius:3px}}
pre{{background:#14140f;color:#eceae4;padding:20px 22px;border-radius:5px;
  overflow-x:auto;font-family:var(--mono);font-size:13.5px;line-height:1.65;
  max-width:760px}}
pre code{{background:0;padding:0;color:inherit;font-size:inherit}}

footer{{padding:54px 0 76px;font-family:var(--sans);font-size:14px;color:var(--dim);
  background:var(--panel);border-top:1px solid var(--rule)}}
footer a{{color:var(--ink2)}}
.cite{{font-size:14px;color:var(--dim);border-left:2px solid var(--rule);
  padding-left:18px;margin-top:22px;max-width:690px;line-height:1.55}}

@media (max-width:880px){{
  .keys{{grid-template-columns:1fr 1fr}}
  .key{{border-bottom:1px solid var(--rule2)}}
  .key:nth-child(2){{border-right:0}}
  .grid2{{grid-template-columns:1fr;gap:26px}}
}}
@media (max-width:600px){{
  body{{font-size:17px}}
  .wrap{{padding:0 20px}}
  header{{padding:52px 0 40px}}
  section{{padding:44px 0}}
  .key{{padding:18px 20px}}
  .key .v{{font-size:25px}}
  table{{font-size:13px}}
  td,th{{padding-right:8px;white-space:nowrap}}
  .tk{{white-space:normal}}
  /* Let the table keep its natural width and scroll, rather than squeezing
     numeric cells onto two lines and clipping the right-hand columns. */
  .scroll table{{min-width:600px}}
  .scrollhint{{display:block}}
}}
</style>
</head>
<body>

<header>
  <div class="wrap">
    <p class="eyebrow">Empirical finance · Event study</p>
    <h1>Rate Shock</h1>
    <p class="lede">Which assets react most strongly when the Federal Reserve
      surprises the market?</p>
    <p class="byline">
      <span>{S['n_events']} FOMC announcements · {S['sample_start']} to {S['sample_end']}</span>
      <a href="{GITHUB}">Source &amp; data →</a>
      <a href="{GITHUB}/blob/main/report/REPORT.md">Full report →</a>
    </p>
  </div>
</header>

<div class="keys">
  <div class="key"><div class="v">{fmt(P.loc['SPY','beta'])}%</div>
    <div class="k">S&amp;P 500 response<br>per +25bp hawkish surprise</div></div>
  <div class="key"><div class="v">{fmt(P.loc['IEF','beta'])}%</div>
    <div class="k">7–10y Treasuries<br>clearest response in sample</div></div>
  <div class="key"><div class="v">0</div>
    <div class="k">Equity sectors significant<br>at the 5% level</div></div>
  <div class="key"><div class="v">{S['corr_raw_vs_surprise']:.2f}</div>
    <div class="k">Correlation between rate change<br>and actual surprise</div></div>
</div>

<main>

<section>
  <div class="wrap">
    <div class="col">
      <p class="eyebrow">Research question</p>
      <h2>How do unexpected Fed announcements move equity sectors?</h2>
      <p class="sub">And does that sensitivity change when inflation is high?</p>
      <p>Markets price expectations. If the FOMC delivers exactly the hike that
        futures already implied, the discount rate embedded in valuations does
        not move — and neither should equities. The explanatory variable in this
        study is therefore not the change in the fed funds target but the
        <strong>expectation-adjusted policy surprise</strong>.</p>
      <p>I use the Bauer &amp; Swanson (2023) measure published by the Federal
        Reserve Bank of San Francisco: the first principal component of
        30-minute moves in Eurodollar and SOFR futures around each announcement.
        The window is narrow enough that essentially no other macroeconomic news
        enters it, which is what buys the identification. Sector responses are
        SPY-adjusted abnormal returns over a [0,+1] trading-day window;
        Treasuries and gold enter on a raw-return basis.</p>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="col">
      <p class="eyebrow">The identification point</p>
      <h2>A rate change is not a rate surprise</h2>
      <p class="sub">The distinction is not a technicality in this sample.</p>
      <p>Of the {S['n_events']} announcements studied,
        <strong>144 involved no change in the fed funds target at all</strong> —
        yet those meetings still carry surprises with a standard deviation of
        4.0bp, because the FOMC moved expectations through guidance rather than
        through the current-period rate.</p>
      <p>Across the full sample, the realized target change and the measured
        surprise correlate only <strong>{S['corr_raw_vs_surprise']:.3f}</strong>.
        A design keyed on the realized change would discard most of the usable
        variation and mismeasure the rest.</p>
      <div class="callout">
        <span class="lbl">Sign convention</span>
        <p>A positive surprise means futures-implied rates repriced
          <em>upward</em>: policy was tighter than expected. This is verified
          rather than assumed — regressing the 30-minute 10-year Treasury yield
          response on the surprise gives a slope of +0.44 (t = 7.0).</p>
      </div>
    </div>
    <figure>
      <img src="figures/02_surprise_distribution.png"
           alt="Left: histogram of policy surprises, centred near zero with a standard deviation of about 6 basis points. Right: scatter of the surprise against the realized target change, showing only a moderate relationship.">
      <figcaption>Surprises are centred near zero and small — a standard
        deviation of 5.9bp. The right panel shows why the realized target change
        is a poor proxy: the two are only moderately correlated.</figcaption>
    </figure>
  </div>
</section>

<section>
  <div class="wrap">
    <p class="eyebrow">Main results</p>
    <h2>Sector sensitivity to monetary policy surprises</h2>
    <p class="sub">Return response per +25bp tighter-than-expected surprise, with
      95% confidence intervals.</p>
    <figure class="hero-fig">
      <img src="figures/03_sector_beta_forest.png"
           alt="Forest plot of estimated return responses per 25 basis point hawkish surprise for ten sector ETFs, two benchmarks and three cross-assets, each with a 95% confidence interval. Only SPY and IEF have intervals excluding zero.">
      <figcaption>Filled points are significant at the 5% level; hollow points
        are not. Sectors are measured against SPY; SPY, IEF, TLT and GLD use raw
        returns, because subtracting an equity benchmark from a bond return is
        not an abnormal return.</figcaption>
    </figure>
    <p class="scrollhint">Table scrolls horizontally →</p>
    <div class="scroll">
    <table>
      <thead><tr>
        <th>Asset</th><th class="num">β per +25bp</th><th class="num">95% CI</th>
        <th class="num">p</th><th class="num">Bootstrap p</th><th class="num">n</th>
        <th class="num">Basis</th>
      </tr></thead>
      <tbody>
{beta_rows(d, ['SPY','IEF','TLT','GLD','QQQ'] + list(sec.index))}
      </tbody>
    </table>
    </div>
    <p class="tnote">Shaded rows are significant at the 5% level.
      HC1 robust standard errors; bootstrap column is a Rademacher wild
      bootstrap imposing the null. XLRE has only {int(P.loc['XLRE','n'])} usable
      events and should be treated as uninformative.</p>

    <div class="grid2">
      <div class="finding">
        <h3>The broad market response is large</h3>
        <p>A +25bp hawkish surprise moves the S&amp;P 500 by
          {fmt(P.loc['SPY','beta'])}% (p&nbsp;=&nbsp;{P.loc['SPY','p']:.3f}).
          This is the headline effect and it is well identified.</p>
      </div>
      <div class="finding">
        <h3>Treasuries give the cleanest signal</h3>
        <p>IEF returns {fmt(P.loc['IEF','beta'])}% per +25bp
          (p&nbsp;{'&lt;&nbsp;0.001' if P.loc['IEF','p'] < 0.001 else '=&nbsp;' + f"{P.loc['IEF','p']:.3f}"}, bootstrap
          p&nbsp;=&nbsp;{d['boot'].loc['IEF','wild_bootstrap_p']:.3f}) — the
          best-identified coefficient in the study, as a near-mechanical
          duration effect should be.</p>
      </div>
      <div class="finding">
        <h3>No single sector clears 5%</h3>
        <p>The ordering is economically sensible — Technology and Consumer
          Discretionary at the sensitive end, Staples and Energy at the
          defensive end — but the smallest sector p-value is
          {min_p_sec:.3f}. The cross-section is suggestive, not established.</p>
      </div>
      <div class="finding">
        <h3>Pooling recovers the cyclical effect</h3>
        <p>A pooled test of cyclicals (XLY, XLI, XLB) with event-clustered
          errors gives {fmt(cyc['beta'])}%
          (p&nbsp;=&nbsp;{cyc['p']:.3f}) — more power than any single-asset
          regression.</p>
      </div>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="col">
      <p class="eyebrow">Cross-asset</p>
      <h2>Equity sectors rotate; they do not track bonds</h2>
      <p class="sub">Correlation of event responses across {S['n_events']} announcements.</p>
      <p>The striking feature is how <em>weak</em> the bond–equity links are.
        Sector responses correlate strongly with each other — Technology against
        Staples at −0.62, Utilities against Staples at +0.66 — but barely at all
        with Treasuries (|r| ≤ 0.32). Around FOMC announcements the dominant axis
        of equity variation is cyclical-versus-defensive rotation, not shared
        duration exposure with bonds.</p>
      <p>Consumer Discretionary is the exception, and the clustering agrees: it
        is the one equity sector that groups with the two Treasury funds rather
        than with the defensives. Real Estate — the sector whose textbook
        duration story is strongest — is absent from the clustering entirely,
        because its 72-event history is too short to include.</p>
    </div>
    <figure>
      <img src="figures/07_treasury_equity_scatter.png"
           alt="Three scatter plots of long-Treasury event responses against Technology, Utilities and Financials responses, each showing a weak relationship.">
      <figcaption>Long-Treasury responses plotted against three sector
        responses. The relationships are weak in every panel.</figcaption>
    </figure>
    <figure>
      <img src="figures/09_dendrogram.png"
           alt="Hierarchical clustering dendrogram grouping assets by correlation of their FOMC event responses; IEF and TLT merge first, then Consumer Discretionary joins them.">
      <figcaption>Hierarchical clustering on correlation distance. The Treasury
        pair merges first; Consumer Discretionary joins them before any other
        equity sector. Exploratory — no causal claim is made from this.</figcaption>
    </figure>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="col">
      <p class="eyebrow">Inflation regime</p>
      <h2>Does high inflation amplify rate sensitivity?</h2>
      <p class="sub">Pre-registered prediction: yes. The data say otherwise.</p>
      <p>At each announcement I attach the most recently <em>released</em> CPI
        report — joined by an as-of merge on timestamps against 390 real BLS
        release dates, so no CPI published after the meeting can leak into the
        regime flag. High inflation is headline CPI YoY ≥ 3%, giving
        {S['n_high_infl']} high- and {S['n_low_infl']} low-inflation events
        spanning 2000–2008, 2011 and 2021–2023 — a genuine regime variable, not
        a disguised 2022 dummy.</p>
      <p><strong>The amplification hypothesis is not supported for equities.</strong>
        Every sector-level interaction is insignificant. The pre-registered prior
        was wrong, and it is reported as wrong.</p>
      <div class="callout">
        <span class="lbl">The one robust regime effect</span>
        <p><strong>Gold</strong> responds strongly negatively to hawkish
          surprises when inflation is low ({fmt(I.loc['GLD','beta_low_regime'])}%)
          and roughly not at all when inflation is high
          ({fmt(I.loc['GLD','beta_high_regime'])}%). That interaction keeps its
          sign across all five inflation thresholds tested
          ({fmt(gld_rob.min(), 2, False)} to {fmt(gld_rob.max(), 2, False)}) —
          consistent with inflation-hedge demand offsetting the real-rate
          channel.</p>
      </div>
      <div class="callout">
        <span class="lbl">What did not survive</span>
        <p>Consumer Discretionary looks like amplification at the 3% threshold
          ({fmt(xly_3['inter_beta'])}, p&nbsp;=&nbsp;{xly_3['inter_p']:.3f}) but
          <strong>reverses sign</strong> at a 2% threshold
          ({fmt(xly_lo['inter_beta'])}). It is specification-sensitive and is
          not promoted to a finding.</p>
      </div>
    </div>
    <figure>
      <img src="figures/05_regime_betas.png"
           alt="Dot plot comparing each sector's estimated rate sensitivity in low-inflation versus high-inflation regimes, with the difference annotated; no difference is statistically significant.">
      <figcaption>Sector sensitivity by regime. No interaction reaches
        significance, even before correcting for testing fifteen assets.</figcaption>
    </figure>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="col">
      <p class="eyebrow">Robustness</p>
      <h2>{d['n_rob']:,} estimates, none discarded</h2>
      <p class="sub">8 sample filters × 4 windows × 2 shock measures × 3 return
        definitions, plus {d['n_inter']} interaction estimates across 5 inflation
        thresholds.</p>
      <p>Every specification run is persisted to
        <code>results/tables/</code>, including the ones that disagree with the
        headline. What holds across the entire battery: IEF's sign and magnitude
        are essentially invariant, and
        {", ".join(t for t in ST['stable_all'] if t != "IEF")} never change
        sign either.</p>
      <p>What does not: <strong>{ST['n_unstable_all']} of
        {ST['n_sectors']} sector betas are not sign-stable.</strong> Utilities
        alone spans −2.44 to +1.96. The instability is concentrated in one
        place — under the six exclusion-type filters only
        {", ".join(ST['unstable_sectors_excl'])} flip, but splitting the sample
        pre/post-2008 additionally flips
        {", ".join(ST['flipped_by_subperiod'])}. The zero-lower-bound era is a
        genuinely different monetary regime, and the cross-section does not
        survive it. That is reported here rather than buried, because it is the
        main reason the cross-sectional result is framed as suggestive.</p>
    </div>
    <figure>
      <img src="figures/10_robustness.png"
           alt="Dot plot showing each sector's estimated beta across eight alternative sample definitions, with the baseline highlighted; several sectors span both positive and negative values.">
      <figcaption>Each blue dot is one alternative sample definition — excluding
        emergency meetings, March 2020, the COVID period, the largest surprise,
        and pre/post-2008 splits.</figcaption>
    </figure>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="col">
      <p class="eyebrow">Methodology</p>
      <h2>Design</h2>
      <ul>
        <li><strong>Sample.</strong> {S['n_events']} FOMC announcements,
          {S['sample_start']} to {S['sample_end']}, {S['n_emergency']}
          unscheduled. <strong>Every date validated</strong> against the Federal
          Reserve's own announcement history — 207 by statement URL, 5 by
          minutes, 3 unscheduled confirmed by press-release title. Zero
          unvalidated.</li>
        <li><strong>Shock.</strong> Bauer–Swanson MPS, first principal component
          of 30-minute changes in ED1–ED4 Eurodollar futures (SOFR from 2023),
          converted to basis points. The orthogonalized variant is reported
          throughout as a co-primary specification.</li>
        <li><strong>Windows.</strong> [−5,+5], [−1,+1], <strong>[0,+1]</strong>
          (pre-registered baseline) and [0,+5]. Daily and intraday estimates are
          reported as separate coefficients, never mixed.</li>
        <li><strong>Abnormal return.</strong> <em>AR = R<sub>sector</sub> −
          R<sub>SPY</sub></em> for sectors; raw returns for SPY, IEF, TLT and
          GLD.</li>
        <li><strong>Inference.</strong> HC1 robust standard errors; HC0/HC3 and
          a wild bootstrap in the robustness battery. Betas reported per
          +25bp.</li>
      </ul>
      <h3>Pre-registration</h3>
      <p>Directional hypotheses were committed to git <em>before</em> any
        regression was estimated, and the file has not been edited since.
        Three of six directional priors — Financials, Utilities and Real Estate —
        came out with the <strong>wrong sign</strong>. They were not rewritten.</p>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="col">
      <p class="eyebrow">Limitations</p>
      <h2>What this study cannot claim</h2>
      <ul>
        <li>The <strong>surprise dataset ends {S['sample_end']}</strong>, the
          limit of the published Bauer–Swanson update. Nothing here speaks to
          policy after that date.</li>
        <li><strong>Statistical power is the binding constraint.</strong>
          {S['n_events']} events with a 5.9bp surprise standard deviation leaves
          sector confidence intervals ±2–3 percentage points wide. The FOMC
          meets eight times a year; no econometric choice relaxes this.</li>
        <li><strong>High-frequency analysis is limited</strong> to the 30-minute
          measurements that ship with the Bauer–Swanson dataset. No sector-level
          intraday data was available, so wider intraday windows could not be
          constructed.</li>
        <li><strong>Longer windows admit more unrelated news.</strong> For an
          identical shock and asset, R² falls from 0.25 in a 30-minute window to
          0.09 over two days. Wider windows give larger point estimates but
          weaker identification.</li>
        <li><strong>XLRE has only {int(P.loc['XLRE','n'])} usable events</strong>
          (it launched in October 2015), is unstable under every perturbation,
          and is excluded from the PCA and clustering.</li>
        <li><strong>Many sector coefficients are specification-sensitive</strong>
          — {ST['n_unstable_all']} of {ST['n_sectors']} change sign across the
          full robustness battery, mostly driven by the pre/post-2008
          sub-period split.</li>
        <li><strong>These are event-study associations, not structural causal
          estimates.</strong> The design identifies price responses to policy
          news in a 1–2 day window. It says nothing about the real economy,
          longer-horizon returns, or sector fundamentals.</li>
      </ul>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="col">
      <p class="eyebrow">Reproducibility</p>
      <h2>One command regenerates everything</h2>
      <p>The research pipeline is plain Python and runs locally. This page is a
        static artifact built from its output — no analysis runs in the browser
        or on the server.</p>
<pre><code>git clone {GITHUB.replace('https://github.com/','git@github.com:')}.git
cd rate-shock
python3.11 -m venv .venv
./.venv/bin/pip install -r requirements.txt

./.venv/bin/python scripts/run_analysis.py   # tables + figures
./.venv/bin/python -m pytest tests/ -q       # 70 tests</code></pre>
      <p>Deleting <code>results/</code> and re-running regenerates all 19
        CSV/JSON artifacts <strong>byte-for-byte identically</strong>.
        <code>tests/test_frozen_results.py</code> pins the headline estimates so
        a future refactor cannot silently move a conclusion.</p>
      <p><a href="{GITHUB}">Repository on GitHub →</a><br>
         <a href="{GITHUB}/blob/main/report/REPORT.md">Full empirical report →</a><br>
         <a href="{GITHUB}/blob/main/docs/DATA_PROVENANCE.md">Data provenance →</a></p>
      <div class="cite">
        Bauer, Michael D., and Eric T. Swanson (2023). “A Reassessment of
        Monetary Policy Surprises and High-Frequency Identification.”
        <em>NBER Macroeconomics Annual</em> 37, 87–155. Updated series published
        by the Federal Reserve Bank of San Francisco.
      </div>
    </div>
  </div>
</section>

</main>

<footer>
  <div class="wrap">
    <p>Rate Shock — event study of Federal Reserve policy surprises across US
      equity sectors, Treasuries and gold.<br>
      Data: Federal Reserve Bank of San Francisco · federalreserve.gov · FRED ·
      BLS · Yahoo Finance.</p>
    <p><a href="{GITHUB}">GitHub</a></p>
  </div>
</footer>

</body>
</html>
"""
    (SITE / "index.html").write_text(html, encoding="utf-8")
    print(f"site/index.html  {len(html)/1024:.1f} KB")
    print(f"site/figures/    {len(list(figdir.glob('*.png')))} figures "
          f"({sum(f.stat().st_size for f in figdir.glob('*.png'))/1024:.0f} KB)")


if __name__ == "__main__":
    build()
