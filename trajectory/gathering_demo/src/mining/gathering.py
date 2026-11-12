"""Gathering detection — Test-and-Divide (TAD, Algorithm 2 of Zheng et al.), ported from
legacy/gathering_core.py.

Participator of a crowd: object present in ≥ k_p of its clusters (bit-vector count). A crowd is a
gathering if every cluster has ≥ m_p participators. Otherwise the violating clusters split it into
consecutive sub-crowds; participators are recomputed on each sub-crowd (only among the parent's
participators — a non-participator of Cr is never one of a sub-crowd) and the test repeats; sub-crowds
shorter than k_c are dropped. Only closed gatherings are returned.
"""
from __future__ import annotations

import numpy as np

from src.mining.crowd import drop_contained
from src.mining.snapshot import Cluster


def tad(crowd: list[int], cl: dict[int, Cluster], k_p: int, m_p: int, k_c: int) -> dict:
    n = len(crowd)
    objs = sorted({o for i in crowd for o in cl[i].members})
    oi = {o: j for j, o in enumerate(objs)}
    B = np.zeros((len(objs), n), dtype=bool)  # bit-vector signatures
    for col, i in enumerate(crowd):
        B[[oi[o] for o in cl[i].members], col] = True
    trace: list[dict] = []
    out: list[list[int]] = []
    out_par: list[list[str]] = []

    def run(mask: np.ndarray, cand: np.ndarray) -> None:
        par = cand & ((B & mask).sum(axis=1) >= k_p)
        counts = np.where(mask, (B & par[:, None]).sum(axis=0), -1)
        bad = [int(i) for i in np.where(mask & (counts < m_p))[0]]
        trace.append(dict(kind="test", mask=mask.copy(), par=[objs[j] for j in np.where(par)[0]],
                          counts=counts.tolist(), bad=bad))
        if not bad:
            out.append([crowd[i] for i in np.where(mask)[0]])
            out_par.append([objs[j] for j in np.where(par)[0]])
            return
        parts, cur = [], None
        for i in range(n):
            if mask[i] and i not in bad:
                if cur is None:
                    cur = np.zeros(n, bool)
                    parts.append(cur)
                cur[i] = True
            else:
                cur = None
        trace.append(dict(kind="divide", mask=mask.copy(), bad=bad,
                          parts=[dict(mask=p, tau=int(p.sum()), ok=bool(p.sum() >= k_c)) for p in parts]))
        for p in parts:
            if p.sum() >= k_c:
                run(p, par)

    run(np.ones(n, bool), np.ones(len(objs), bool))
    return dict(objs=objs, B=B, trace=trace, gatherings=out, participators=out_par)


def closed_gatherings(tads: list[dict]) -> list[tuple[list[int], list[str], int]]:
    """Flatten TAD outputs → (cluster ids, participators, crowd index), dropping contained ones."""
    allg = [(g, p, ci) for ci, td in enumerate(tads) for g, p in zip(td["gatherings"], td["participators"],
                                                                      strict=True)]
    keep = {tuple(s) for s in drop_contained([g for g, _, _ in allg])}
    seen, out = set(), []
    for g, p, ci in allg:
        if tuple(g) in keep and tuple(g) not in seen:
            seen.add(tuple(g))
            out.append((g, p, ci))
    return out
