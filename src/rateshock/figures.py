"""All report figures.

Palette follows the validated reference instance: categorical slots
blue/orange/aqua (validated all-pairs for scatter-type forms), a blue
sequential ramp, and a blue<->red diverging pair with a neutral gray midpoint
for signed magnitudes. Identity is never carried by color alone -- every
categorical form is direct-labeled or legended.
"""
from __future__ import annotations

import textwrap

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from scipy.cluster.hierarchy import dendrogram

from .config import FIGURES, SECTORS

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#8a8983"
GRID = "#e6e5e1"
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
POS, NEG, MID = "#2a78d6", "#e34948", "#f0efec"
DIVERGING = LinearSegmentedColormap.from_list("bwr_ds", [NEG, MID, POS])

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "font.size": 10,
    "text.color": INK, "axes.labelcolor": INK2, "axes.edgecolor": GRID,
    "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.7,
    "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False, "figure.dpi": 140,
})


def _save(fig, name: str) -> str:
    path = FIGURES / name
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return str(path)


def _title(ax, title: str, subtitle: str = "", width: int = 104):
    """Left-aligned title/subtitle anchored in POINTS above the axes.

    Offsetting in points rather than axes fractions keeps the spacing constant
    across figures of very different heights (the forest plots grow with the
    number of assets), so the two lines never collide.
    """
    sub = textwrap.wrap(subtitle, width) if subtitle else []
    base = 8 + 11.5 * len(sub)
    ax.annotate(title, xy=(0, 1), xycoords="axes fraction",
                xytext=(0, base), textcoords="offset points",
                fontsize=12.5, fontweight="bold", color=INK,
                ha="left", va="bottom", annotation_clip=False)
    for i, line in enumerate(sub):
        ax.annotate(line, xy=(0, 1), xycoords="axes fraction",
                    xytext=(0, base - 11.5 * (i + 1)), textcoords="offset points",
                    fontsize=9.2, color=INK2, ha="left", va="bottom",
                    annotation_clip=False)


def _right_label(ax, y, text: str, color=INK2, size=8.6):
    """Label pinned to the right edge of the axes, immune to xlim changes."""
    ax.annotate(text, xy=(1, y), xycoords=("axes fraction", "data"),
                xytext=(8, 0), textcoords="offset points", va="center",
                fontsize=size, color=color, annotation_clip=False)


# ---------------------------------------------------------------- 1. timeline
def fig_event_timeline(events: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(11, 4.0))
    e = events.dropna(subset=["surprise_bps"])
    sched = e[~e["emergency"].astype(bool)]
    emer = e[e["emergency"].astype(bool)]
    ax.vlines(sched["meeting_date"], 0, sched["surprise_bps"], color=S1,
              lw=1.6, alpha=0.85, label=f"Scheduled (n={len(sched)})")
    ax.vlines(emer["meeting_date"], 0, emer["surprise_bps"], color=S2,
              lw=2.2, label=f"Unscheduled (n={len(emer)})")
    ax.scatter(emer["meeting_date"], emer["surprise_bps"], color=S2, s=26,
               zorder=3, edgecolor=SURFACE, linewidth=1.2)
    hi = e[e["high_inflation"] == 1]
    for _, r in hi.iterrows():
        ax.axvspan(r["meeting_date"] - pd.Timedelta(days=12),
                   r["meeting_date"] + pd.Timedelta(days=12),
                   color=S3, alpha=0.10, lw=0, zorder=0)
    ax.axhline(0, color=MUTED, lw=1)
    ax.set_ylabel("Policy surprise (bp)")
    ax.legend(loc="lower left", ncol=2)
    _title(ax, "FOMC event timeline and policy surprises",
           "Bauer-Swanson MPS, 30-min window. Each green band marks one event "
           "classified high-inflation (latest RELEASED CPI YoY >= 3% as of the "
           "announcement). Positive = tighter than expected.")
    return _save(fig, "01_event_timeline.png")


# ------------------------------------------------------------ 2. distribution
def fig_surprise_distribution(events: pd.DataFrame) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.0))
    e = events.dropna(subset=["surprise_bps"])
    ax = axes[0]
    ax.hist(e["surprise_bps"], bins=40, color=S1, alpha=0.9, edgecolor=SURFACE)
    ax.axvline(0, color=MUTED, lw=1)
    ax.set_xlabel("Surprise (bp)"); ax.set_ylabel("FOMC events")
    _title(ax, "Distribution of policy surprises",
           f"n={len(e)}, sd={e['surprise_bps'].std():.1f}bp, "
           f"range [{e['surprise_bps'].min():.0f}, {e['surprise_bps'].max():.0f}]bp")
    ax = axes[1]
    ax.scatter(e["raw_change_bps"], e["surprise_bps"], s=26, color=S1,
               alpha=0.75, edgecolor=SURFACE, linewidth=0.6)
    ax.axhline(0, color=MUTED, lw=1); ax.axvline(0, color=MUTED, lw=1)
    ax.set_xlabel("Raw target change (bp)"); ax.set_ylabel("Surprise (bp)")
    corr = e[["raw_change_bps", "surprise_bps"]].corr().iloc[0, 1]
    _title(ax, "A rate change is not a rate surprise",
           f"correlation = {corr:.2f}. Most target moves were largely anticipated.")
    return _save(fig, "02_surprise_distribution.png")


# ------------------------------------------------------- 3. HERO forest plot
def fig_forest(betas: pd.DataFrame, fname: str = "03_sector_beta_forest.png",
               title: str = "Sector sensitivity to monetary policy surprises",
               subtitle: str | None = None) -> str:
    d = betas.dropna(subset=["beta"]).sort_values("beta").reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(9.5, 0.46 * len(d) + 2.4))
    y = np.arange(len(d))
    sig = d["p"] < 0.05
    ax.hlines(y, d["ci_low"], d["ci_high"], color=S1, lw=2.0, alpha=0.85)
    ax.scatter(d.loc[sig, "beta"], y[sig.to_numpy()], s=64, color=S1, zorder=3,
               edgecolor=SURFACE, linewidth=1.4, label="p < 0.05")
    ax.scatter(d.loc[~sig, "beta"], y[(~sig).to_numpy()], s=64,
               facecolor=SURFACE, edgecolor=S1, linewidth=1.8, zorder=3,
               label="not significant")
    ax.axvline(0, color=MUTED, lw=1.2)
    labels = [f"{t}  {SECTORS.get(t, '')}".strip() for t in d["ticker"]]
    ax.set_yticks(y); ax.set_yticklabels(labels)
    ax.set_ylim(-0.8, len(d) - 0.2)
    for i, r in d.iterrows():
        _right_label(ax, i, f"{r['beta']:+.2f}  (n={int(r['n'])})")
    ax.set_xlabel("Return response per +25bp hawkish surprise (%)")
    ax.legend(loc="lower right")
    _title(ax, title, subtitle or
           "Points are OLS betas; bars are 95% CIs (HC1 robust). Sectors are "
           "SPY-adjusted; SPY/IEF/TLT/GLD are raw returns.")
    return _save(fig, fname)


# ----------------------------------------------------------- 4. CAR curves
def fig_car_curves(paths: pd.DataFrame, events: pd.DataFrame,
                   tickers=("XLK", "XLU", "XLF", "XLP")) -> str:
    ev = events.dropna(subset=["surprise_bps"]).copy()
    hawk = set(ev.loc[ev["surprise_bps"] > ev["surprise_bps"].quantile(0.8),
                      "meeting_id"])
    dove = set(ev.loc[ev["surprise_bps"] < ev["surprise_bps"].quantile(0.2),
                      "meeting_id"])
    fig, axes = plt.subplots(1, len(tickers), figsize=(3.0 * len(tickers), 3.9),
                             sharey=True)
    for ax, tk in zip(np.atleast_1d(axes), tickers):
        g = paths[paths["ticker"] == tk]
        for grp, color, lab in ((hawk, S2, "Hawkish quintile"),
                                (dove, S1, "Dovish quintile")):
            m = g[g["meeting_id"].isin(grp)].groupby("rel_day")["car_adj"].mean()
            ax.plot(m.index, m.to_numpy(), color=color, lw=2.0, label=lab)
        ax.axvline(0, color=MUTED, lw=1, ls="--")
        ax.axhline(0, color=MUTED, lw=1)
        ax.set_title(f"{tk}  {SECTORS.get(tk,'')}", loc="left", fontsize=10,
                     color=INK)
        ax.set_xlabel("Trading days from announcement")
    np.atleast_1d(axes)[0].set_ylabel("Mean CAR vs SPY (%)")
    np.atleast_1d(axes)[0].legend(loc="best", fontsize=8.5)
    fig.suptitle("Event-time cumulative abnormal returns, hawkish vs dovish "
                 "surprise quintiles", x=0.005, y=1.02, ha="left",
                 fontsize=12.5, fontweight="bold", color=INK)
    return _save(fig, "04_car_curves.png")


# -------------------------------------------------- 5. regime beta comparison
def fig_regime_betas(inter: pd.DataFrame) -> str:
    d = inter.dropna(subset=["beta_low_regime", "beta_high_regime"]).copy()
    d = d[d["ticker"].isin(SECTORS)].sort_values("beta_low_regime")
    fig, ax = plt.subplots(figsize=(10, 0.52 * len(d) + 2.4))
    y = np.arange(len(d))
    ax.hlines(y, d["beta_low_regime"], d["beta_high_regime"], color=GRID, lw=2.4,
              zorder=1)
    ax.scatter(d["beta_low_regime"], y, s=66, color=S1, zorder=3,
               edgecolor=SURFACE, linewidth=1.3, label="Low inflation (CPI < 3%)")
    ax.scatter(d["beta_high_regime"], y, s=66, color=S2, zorder=3, marker="D",
               edgecolor=SURFACE, linewidth=1.3, label="High inflation (CPI >= 3%)")
    ax.axvline(0, color=MUTED, lw=1.2)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{t}  {SECTORS.get(t,'')}" for t in d["ticker"]])
    for i, (_, r) in enumerate(d.iterrows()):
        star = " *" if r["inter_p"] < 0.05 else ""
        _right_label(ax, i, f"Δ={r['inter_beta']:+.2f}{star}")
    ax.set_xlabel("Return response per +25bp hawkish surprise (%)")
    ax.legend(loc="lower right")
    _title(ax, "Sector rate sensitivity by inflation regime",
           "Δ is the interaction coefficient (high minus low); * marks p<0.05 "
           "before multiple-testing correction.")
    return _save(fig, "05_regime_betas.png")


# ------------------------------------------------------------- 6. heatmap
def fig_response_heatmap(mat: pd.DataFrame, events: pd.DataFrame) -> str:
    ev = events.set_index("meeting_id")
    m = mat.loc[[i for i in mat.index if i in ev.index]]
    order = ev.loc[m.index, "meeting_date"].sort_values().index
    m = m.loc[order]
    lim = float(np.nanpercentile(np.abs(m.to_numpy()), 98))
    fig, ax = plt.subplots(figsize=(9.0, 10.5))
    im = ax.imshow(m.to_numpy(), aspect="auto", cmap=DIVERGING,
                   norm=TwoSlopeNorm(vmin=-lim, vcenter=0, vmax=lim),
                   interpolation="nearest")
    ax.set_xticks(range(m.shape[1]))
    ax.set_xticklabels(m.columns, rotation=90, fontsize=8)
    step = max(1, len(m) // 26)
    ax.set_yticks(range(0, len(m), step))
    ax.set_yticklabels([ev.loc[i, "meeting_date"].strftime("%Y-%m-%d")
                        for i in m.index[::step]], fontsize=7.4)
    ax.grid(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.030, pad=0.02)
    cb.set_label("Event response (%)", color=INK2)
    cb.outline.set_visible(False)
    _title(ax, "Asset x event response heatmap",
           "[0,+1] window. Sectors benchmark-adjusted; cross-assets raw. "
           "Blue = up, red = down.")
    return _save(fig, "06_response_heatmap.png")


# ------------------------------------------------- 7. treasury/equity scatter
def fig_treasury_equity_scatter(mat: pd.DataFrame, events: pd.DataFrame) -> str:
    ev = events.set_index("meeting_id")
    pairs = [("TLT", "XLK", S1), ("TLT", "XLU", S2), ("TLT", "XLF", S3)]
    fig, axes = plt.subplots(1, 3, figsize=(12.4, 4.2), sharex=True)
    for ax, (xk, yk, col) in zip(axes, pairs):
        if xk not in mat.columns or yk not in mat.columns:
            continue
        d = mat[[xk, yk]].dropna()
        ax.scatter(d[xk], d[yk], s=26, color=col, alpha=0.7,
                   edgecolor=SURFACE, linewidth=0.6)
        if len(d) > 3:
            b = np.polyfit(d[xk], d[yk], 1)
            xs = np.linspace(d[xk].min(), d[xk].max(), 50)
            ax.plot(xs, np.polyval(b, xs), color=INK2, lw=1.6, ls="--")
            r = d.corr().iloc[0, 1]
            ax.text(0.03, 0.95, f"r = {r:+.2f}   n = {len(d)}",
                    transform=ax.transAxes, va="top", fontsize=9, color=INK2)
        ax.axhline(0, color=MUTED, lw=0.9); ax.axvline(0, color=MUTED, lw=0.9)
        ax.set_xlabel(f"{xk} raw response (%)")
        ax.set_ylabel(f"{yk} response vs SPY (%)")
        ax.set_title(f"{xk} vs {yk}", loc="left", fontsize=10.5, color=INK)
    fig.suptitle("Treasury versus equity-sector responses across FOMC events",
                 x=0.005, y=1.02, ha="left", fontsize=12.5, fontweight="bold",
                 color=INK)
    return _save(fig, "07_treasury_equity_scatter.png")


# ------------------------------------------------------------- 8. PCA
def fig_pca(loadings: pd.DataFrame, evr: pd.Series, labels: pd.Series) -> str:
    """Asset loadings on PC1/PC2, coloured AND shaped by cluster.

    Cluster identity is carried by marker shape as well as hue, so the fourth
    cluster does not depend on a low-chroma gray being distinguishable, and
    every point is direct-labeled with its ticker.
    """
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.9),
                             gridspec_kw={"width_ratios": [1.4, 1]})
    ax = axes[0]
    palette = [S1, S2, S3, INK2]
    markers = ["o", "s", "^", "D"]
    for cl in sorted(labels.unique()):
        idx = [i for i in labels[labels == cl].index if i in loadings.index]
        ax.scatter(loadings.loc[idx, "PC1"], loadings.loc[idx, "PC2"], s=92,
                   color=palette[(cl - 1) % len(palette)],
                   marker=markers[(cl - 1) % len(markers)],
                   edgecolor=SURFACE, linewidth=1.4, zorder=3,
                   label=f"Cluster {cl}: " + ", ".join(idx))

    # Greedy label declutter: nudge a label downward when it would land on a
    # neighbour already placed (XLK/QQQ sit almost on top of each other).
    placed: list[tuple[float, float]] = []
    xr = float(loadings["PC1"].max() - loadings["PC1"].min()) or 1.0
    yr = float(loadings["PC2"].max() - loadings["PC2"].min()) or 1.0
    for tk, r in loadings.sort_values(["PC2", "PC1"], ascending=False).iterrows():
        dy = 5
        for px, py in placed:
            if (abs(r["PC1"] - px) / xr < 0.10
                    and abs(r["PC2"] - py) / yr < 0.055):
                dy = -13
                break
        ax.annotate(tk, (r["PC1"], r["PC2"]), fontsize=9, color=INK,
                    xytext=(7, dy), textcoords="offset points")
        placed.append((r["PC1"], r["PC2"]))

    ax.axhline(0, color=MUTED, lw=0.9); ax.axvline(0, color=MUTED, lw=0.9)
    ax.set_xlabel(f"PC1 loading ({evr.iloc[0]*100:.0f}% of variance)")
    ax.set_ylabel(f"PC2 loading ({evr.iloc[1]*100:.0f}%)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), fontsize=8.2,
              ncol=2)
    _title(ax, "PCA of asset responses across FOMC events",
           "Assets positioned by loading on the first two components. "
           "Exploratory: this is a description of co-movement, not a causal "
           "grouping.")
    ax = axes[1]
    ax.bar(range(1, len(evr) + 1), evr.to_numpy() * 100, color=S1,
           edgecolor=SURFACE)
    ax.set_xticks(range(1, len(evr) + 1))
    ax.set_xticklabels(evr.index)
    ax.set_ylabel("Variance explained (%)")
    for i, v in enumerate(evr.to_numpy() * 100, start=1):
        ax.text(i, v, f"{v:.0f}%", ha="center", va="bottom", fontsize=9,
                color=INK2)
    _title(ax, "Scree", "No dominant single factor: PC1 explains only "
                        f"{evr.iloc[0]*100:.0f}%.")
    return _save(fig, "08_pca_projection.png")


# ------------------------------------------------------------ 9. dendrogram
def fig_dendrogram(Z, corr: pd.DataFrame, n_clusters: int = 4) -> str:
    fig, ax = plt.subplots(figsize=(10, 4.8))
    dendrogram(Z, labels=list(corr.index), ax=ax, color_threshold=None,
               link_color_func=lambda k: INK2, leaf_font_size=10)
    ax.set_ylabel("Correlation distance (1 - r)")
    ax.grid(axis="x", visible=False)
    _title(ax, "Hierarchical clustering of assets by FOMC event response",
           "Average linkage on 1 - correlation of event responses. Exploratory.")
    return _save(fig, "09_dendrogram.png")


# ---------------------------------------------------------- 10. robustness
def fig_robustness(rob: pd.DataFrame, tickers=None) -> str:
    """Dispersion of each sector beta across alternative sample definitions.

    Every alternative sample is drawn in the same blue on purpose: the question
    this figure answers is "how much does the estimate move when the sample is
    perturbed", not "which perturbation is which". Encoding eight specs by hue
    would put identity on color alone and none of those hues would be
    separable. The per-spec values are in results/tables/robustness_all.csv.
    """
    # Keep only the HC1 primary estimate per (sample, ticker): the battery also
    # stores HC0/HC3 re-estimates of the baseline, which are the SAME point
    # estimate and would otherwise be plotted as if they were extra samples.
    d = rob[(rob["dep_mode"] == "auto") & (rob["shock"] == "surprise_bps")
            & (rob["window"] == "d0_p1")
            & (rob["spec"] == rob["sample"])].dropna(subset=["beta"])
    d = d.drop_duplicates(subset=["ticker", "sample"])
    base = d[d["sample"] == "baseline"].set_index("ticker")["beta"]
    tickers = tickers or [t for t in SECTORS if t in set(d["ticker"])]
    tickers = [t for t in sorted(tickers, key=lambda t: base.get(t, 0.0))]
    d = d[d["ticker"].isin(tickers)]
    alts = d[d["sample"] != "baseline"]
    n_specs = alts["sample"].nunique()

    fig, ax = plt.subplots(figsize=(10.5, 0.52 * len(tickers) + 2.6))
    ypos = {t: i for i, t in enumerate(tickers)}
    for t, i in ypos.items():
        ax.axhspan(i - 0.46, i + 0.46, color=GRID, alpha=0.30, lw=0, zorder=0)
        g = alts[alts["ticker"] == t]["beta"]
        if len(g):
            ax.hlines(i, g.min(), g.max(), color=S1, alpha=0.35, lw=1.4,
                      zorder=1)
    rng = np.random.default_rng(7)
    ax.scatter(alts["beta"],
               [ypos[t] + rng.uniform(-0.17, 0.17) for t in alts["ticker"]],
               s=30, color=S1, alpha=0.65, edgecolor=SURFACE, linewidth=0.6,
               zorder=2, label=f"Alternative sample ({n_specs} specifications)")
    bb = d[d["sample"] == "baseline"]
    ax.scatter(bb["beta"], [ypos[t] for t in bb["ticker"]], s=78, color=S2,
               edgecolor=SURFACE, linewidth=1.3, zorder=4, label="Baseline")
    ax.axvline(0, color=MUTED, lw=1.2)
    ax.set_yticks(list(ypos.values()))
    ax.set_yticklabels([f"{t}  {SECTORS.get(t,'')}" for t in ypos])
    ax.set_ylim(-0.7, len(tickers) - 0.3)
    ax.set_xlabel("Beta per +25bp hawkish surprise (%)")
    ax.legend(loc="lower right")
    _title(ax, "Robustness of sector betas across sample definitions",
           "[0,+1] window, raw MPS shock. Each blue dot is one alternative "
           "sample (excluding emergency meetings, March 2020, COVID, the "
           "largest surprise, and pre/post-2008 splits). Line spans the range.")
    return _save(fig, "10_robustness.png")
