"""Snapshot clusters: DBSCAN at every timestamp on players that are alive and have landed
(the cleaned positions table already contains only those)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN


@dataclass
class Cluster:
    id: int  # global id within one mining run (0, 1, …), ordered by (t, k)
    t: int  # timestamp (s)
    k: int  # index among the clusters of the same timestamp (1, 2, …)
    members: tuple[str, ...]  # player ids, sorted
    pts: np.ndarray  # (n, 2) meters, same order as members

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def centroid(self) -> tuple[float, float]:
        c = self.pts.mean(axis=0)
        return float(c[0]), float(c[1])

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        lo, hi = self.pts.min(axis=0), self.pts.max(axis=0)
        return float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1])


def snapshot_clusters(positions: pd.DataFrame, eps: float, min_pts: int) -> tuple[list[Cluster], pd.DataFrame]:
    """Return (clusters ordered by t then smallest member, labels table t/player/cluster with -1 = noise)."""
    clusters: list[Cluster] = []
    labels = np.full(len(positions), -1, dtype=int)
    pos = positions.reset_index(drop=True)
    for t, g in pos.groupby("t", sort=True):
        if len(g) < min_pts:
            continue
        X = g[["x", "y"]].to_numpy()
        lab = DBSCAN(eps=eps, min_samples=min_pts).fit_predict(X)
        groups = []
        for c in set(lab) - {-1}:
            idx = np.where(lab == c)[0]
            players = g["player"].to_numpy()[idx]
            order = np.argsort(players)
            groups.append((tuple(players[order]), X[idx][order], g.index.to_numpy()[idx]))
        groups.sort(key=lambda m: m[0][0])
        for k, (members, pts, rows) in enumerate(groups, 1):
            cid = len(clusters)
            clusters.append(Cluster(cid, int(t), k, members, pts))
            labels[rows] = cid
    lab_df = pos[["t", "player", "team", "x", "y"]].copy()
    lab_df["cluster"] = labels
    return clusters, lab_df
