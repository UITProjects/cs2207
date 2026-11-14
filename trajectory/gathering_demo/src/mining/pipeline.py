"""run_pipeline(tables, params) → MiningResult consumed by the app, the analytics and the scripts."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.mining.crowd import Link, discover_crowds
from src.mining.gathering import closed_gatherings, tad
from src.mining.snapshot import Cluster, snapshot_clusters

PARAM_KEYS = ("eps", "min_pts", "m_c", "delta", "k_c", "k_p", "m_p")


@dataclass
class MiningResult:
    params: dict
    clusters: list[Cluster]
    labels: pd.DataFrame
    links: list[Link]
    crowds: list[list[int]]
    tads: list[dict]
    gatherings: list[tuple[list[int], list[str], int]]
    crowd_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    gathering_df: pd.DataFrame = field(default_factory=pd.DataFrame)

    def cluster(self, cid: int) -> Cluster:
        return self.clusters[cid]


def _summary(res: MiningResult, seqs: list[list[int]], zones: pd.DataFrame | None, kind: str,
             pars: list[list[str]] | None = None) -> pd.DataFrame:
    rows = []
    for i, s in enumerate(seqs):
        cs = [res.clusters[c] for c in s]
        pts = np.vstack([c.pts for c in cs])
        cen = pts.mean(axis=0)
        members = sorted({m for c in cs for m in c.members})
        row = dict(id=i, t_start=cs[0].t, t_end=cs[-1].t, lifetime=len(cs), mean_size=float(np.mean([c.size for c in cs])),
                   max_size=max(c.size for c in cs), n_objects=len(members), cx=float(cen[0]), cy=float(cen[1]),
                   radius=float(np.percentile(np.linalg.norm(pts - cen, axis=1), 90)),
                   teams=None, clusters=list(s))
        if pars is not None:
            row["n_participators"] = len(pars[i])
            row["participators"] = pars[i]
        rows.append(row)
    df = pd.DataFrame(rows)
    if len(df) and zones is not None and len(zones):
        idx = np.clip(np.searchsorted(zones["t"].to_numpy(), df["t_start"].to_numpy(), side="right") - 1, 0, None)
        df["phase"] = zones["phase"].to_numpy()[idx]
    elif len(df):
        df["phase"] = 0
    return df


def collapse_branches(crowds: list[list[int]], clusters: list[Cluster]) -> tuple[list[list[int]], list[int]]:
    """Closed crowds that only differ by which branch they took when a cluster split (same span, same set of
    people) are one movement pattern: keep the first, count the variants. E.g. a final circle splitting into two
    disjoint groups at 6 steps gives 2^6 = 64 valid closed crowds → 1."""
    cl = {c.id: c for c in clusters}
    seen: dict[tuple, int] = {}
    kept: list[list[int]] = []
    variants: list[int] = []
    for s in crowds:
        key = (cl[s[0]].t, cl[s[-1]].t, frozenset(m for i in s for m in cl[i].members))
        if key in seen:
            variants[seen[key]] += 1
            continue
        seen[key] = len(kept)
        kept.append(s)
        variants.append(1)
    return kept, variants


def run_pipeline(tables: dict, params: dict) -> MiningResult:
    p = {k: params[k] for k in PARAM_KEYS}
    pos = tables["positions"]
    dt = int(tables.get("meta", {}).get("dt", 10))
    clusters, labels = snapshot_clusters(pos, p["eps"], p["min_pts"])
    crowds, links = discover_crowds(clusters, p["m_c"], p["k_c"], p["delta"], dt)
    crowds, variants = collapse_branches(crowds, clusters)
    cl = {c.id: c for c in clusters}
    tads = [tad(cr, cl, p["k_p"], p["m_p"], p["k_c"]) for cr in crowds]
    gath = closed_gatherings(tads)
    res = MiningResult(p, clusters, labels, links, crowds, tads, gath)
    zones = tables.get("zones")
    res.crowd_df = _summary(res, crowds, zones, "crowd")
    if len(res.crowd_df):
        res.crowd_df["variants"] = variants
    res.gathering_df = _summary(res, [g for g, _, _ in gath], zones, "gathering", [pp for _, pp, _ in gath])
    if len(res.gathering_df):
        res.gathering_df["crowd"] = [ci for _, _, ci in gath]
        team_of = dict(zip(pos["player"], pos["team"], strict=False))
        res.gathering_df["teams"] = [sorted({team_of[m] for m in pp}) for pp in res.gathering_df["participators"]]
    return res
