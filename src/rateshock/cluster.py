"""Exploratory structure: PCA and hierarchical clustering of event responses.

This is descriptive only. Nothing here is a causal statement -- the question is
simply whether assets that we believe share a rate-sensitivity mechanism also
group together empirically.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import dendrogram, fcluster, linkage
from scipy.spatial.distance import squareform
from sklearn.decomposition import PCA

from .config import RANDOM_SEED


def balanced_matrix(mat: pd.DataFrame, min_events: int = 100) -> pd.DataFrame:
    """Drop short-history assets, then drop events with any remaining gap.

    PCA needs a complete matrix. Imputing would invent responses for assets
    that did not exist, so we shrink the asset set instead and report what was
    dropped.
    """
    keep = [c for c in mat.columns if mat[c].notna().sum() >= min_events]
    sub = mat[keep].dropna(axis=0, how="any")
    return sub


def run_pca(mat: pd.DataFrame, n_components: int = 5):
    """PCA on the standardized asset x event responses (assets as points)."""
    z = (mat - mat.mean()) / mat.std(ddof=1)
    n_components = min(n_components, min(z.shape) - 1 if min(z.shape) > 1 else 1)
    p = PCA(n_components=n_components, random_state=RANDOM_SEED)
    scores = p.fit_transform(z.values)          # events x components
    loadings = pd.DataFrame(p.components_.T, index=z.columns,
                            columns=[f"PC{i+1}" for i in range(n_components)])
    evr = pd.Series(p.explained_variance_ratio_,
                    index=[f"PC{i+1}" for i in range(n_components)])
    scores = pd.DataFrame(scores, index=z.index,
                          columns=[f"PC{i+1}" for i in range(n_components)])
    return loadings, evr, scores


def cluster_assets(mat: pd.DataFrame, method: str = "average",
                   n_clusters: int = 4):
    """Hierarchical clustering of assets on correlation distance."""
    corr = mat.corr()
    dist = (1.0 - corr).to_numpy(copy=True)
    np.fill_diagonal(dist, 0.0)
    dist = (dist + dist.T) / 2.0                 # enforce exact symmetry
    dist = np.clip(dist, 0.0, None)
    Z = linkage(squareform(dist, checks=False), method=method)
    labels = pd.Series(fcluster(Z, n_clusters, criterion="maxclust"),
                       index=corr.index, name="cluster")
    return Z, labels, corr
