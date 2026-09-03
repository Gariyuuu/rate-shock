#!/usr/bin/env python
"""Run the full rate-shock pipeline: data -> estimates -> tables -> figures."""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from rateshock import cluster, crossasset, figures, robustness
from rateshock.config import (ALL_TICKERS, CROSS_ASSETS, DAILY_WINDOWS,
                              INFLATION_THRESHOLD, PRIMARY_WINDOW, PROCESSED,
                              SECTORS, TABLES, FIGURES)
from rateshock.cpi import attach_inflation_regime, cpi_releases
from rateshock.dataset import build, paths
from rateshock.regressions import (interaction_betas, merge_panel,
                                   pooled_test, primary_betas)


def main() -> None:
    out: dict = {}
    print("[1/8] building dataset ...")
    events, prices, panel, df = build()
    releases = cpi_releases()

    out["n_events"] = int(len(events))
    out["sample_start"] = str(events["meeting_date"].min().date())
    out["sample_end"] = str(events["meeting_date"].max().date())
    out["n_emergency"] = int(events["emergency"].sum())
    out["n_high_infl"] = int(events["high_inflation"].sum())
    out["n_low_infl"] = int((events["high_inflation"] == 0).sum())
    out["surprise_sd_bps"] = float(events["surprise_bps"].std())
    out["surprise_min_bps"] = float(events["surprise_bps"].min())
    out["surprise_max_bps"] = float(events["surprise_bps"].max())
    out["all_dates_validated"] = bool(events["date_validated_official"].all())
    out["corr_raw_vs_surprise"] = float(
        events[["raw_change_bps", "surprise_bps"]].corr().iloc[0, 1])

    print("[2/8] primary regressions ...")
    prim_all = []
    for w in DAILY_WINDOWS:
        for shock in ("surprise_bps", "surprise_orth_bps"):
            r = primary_betas(df, window=w, shock=shock, label="primary")
            prim_all.append(r)
    prim_all = pd.concat(prim_all, ignore_index=True)
    prim_all.to_csv(TABLES / "primary_betas_all_windows.csv", index=False)
    primary = primary_betas(df)
    primary.to_csv(TABLES / "primary_betas.csv", index=False)

    # Pooled group tests (more power than any single asset).
    groups = {
        "long_duration_sectors": ["XLK", "XLU", "XLRE"],
        "cyclicals": ["XLY", "XLI", "XLB"],
        "defensives": ["XLP", "XLV", "XLU"],
        "all_sectors": list(SECTORS),
    }
    pooled = pd.concat([pooled_test(df, g).assign(name=k)
                        for k, g in groups.items()], ignore_index=True)
    pooled.to_csv(TABLES / "pooled_group_tests.csv", index=False)

    print("[3/8] inflation interactions ...")
    inter = interaction_betas(df)
    inter.to_csv(TABLES / "interaction_betas.csv", index=False)

    print("[4/8] cross-asset ...")
    mat = crossasset.response_matrix(df)
    mat.to_csv(PROCESSED / "response_matrix.csv")
    corr = crossasset.event_correlations(mat)
    corr.to_csv(TABLES / "cross_asset_correlation.csv")
    crossasset.overlap_counts(mat).to_csv(TABLES / "cross_asset_overlap.csv")

    print("[5/8] PCA + clustering ...")
    bal = cluster.balanced_matrix(mat)
    out["pca_assets"] = list(bal.columns)
    out["pca_n_events"] = int(len(bal))
    out["pca_dropped_assets"] = [c for c in mat.columns if c not in bal.columns]
    loadings, evr, scores = cluster.run_pca(bal)
    loadings.to_csv(TABLES / "pca_loadings.csv")
    evr.to_frame("explained_variance_ratio").to_csv(TABLES / "pca_variance.csv")
    Z, labels, ccorr = cluster.cluster_assets(bal)
    labels.to_frame().to_csv(TABLES / "asset_clusters.csv")
    out["clusters"] = {str(k): sorted(labels[labels == k].index)
                       for k in sorted(labels.unique())}

    print("[6/8] robustness battery ...")
    rob = robustness.run_battery(df, events)
    rob.to_csv(TABLES / "robustness_all.csv", index=False)
    out["n_robustness_estimates"] = int(len(rob))

    def rebuild(thr: float) -> pd.DataFrame:
        ev2 = attach_inflation_regime(
            events.drop(columns=[c for c in events.columns
                                 if c.startswith(("cpi_", "latest_", "high_"))],
                        errors="ignore"),
            releases, threshold=thr)
        return merge_panel(panel, ev2)

    inter_rob = robustness.run_interaction_battery(df, events, rebuild)
    inter_rob.to_csv(TABLES / "robustness_interaction.csv", index=False)
    out["n_interaction_estimates"] = int(len(inter_rob))

    boot = robustness.bootstrap_table(df)
    boot.to_csv(TABLES / "wild_bootstrap.csv", index=False)

    print("[7/8] figures ...")
    made = []
    made.append(figures.fig_event_timeline(events))
    made.append(figures.fig_surprise_distribution(events))
    made.append(figures.fig_forest(primary))
    ep = paths(events, prices)
    ep.to_csv(PROCESSED / "event_time_paths.csv", index=False)
    made.append(figures.fig_car_curves(ep, events))
    made.append(figures.fig_regime_betas(inter))
    made.append(figures.fig_response_heatmap(mat, events))
    made.append(figures.fig_treasury_equity_scatter(mat, events))
    made.append(figures.fig_pca(loadings, evr, labels))
    made.append(figures.fig_dendrogram(Z, ccorr))
    made.append(figures.fig_robustness(rob))
    out["figures"] = [Path(m).name for m in made]

    print("[8/8] summary ...")
    out["primary"] = primary.set_index("ticker").round(4).to_dict("index")
    out["interaction"] = inter.set_index("ticker").round(4).to_dict("index")
    out["pooled"] = pooled.round(4).to_dict("records")
    out["explained_variance"] = evr.round(4).to_dict()
    (TABLES / "summary.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"\nDone. {len(made)} figures, "
          f"{len(list(TABLES.glob('*.csv')))} tables.")
    print(f"Robustness estimates persisted: {out['n_robustness_estimates']}")


if __name__ == "__main__":
    main()
