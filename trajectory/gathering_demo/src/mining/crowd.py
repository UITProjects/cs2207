"""Crowd discovery — Algorithm 1 of Zheng et al. (ICDE 2013), ported from legacy/gathering_core.py.

A crowd is a sequence of clusters at consecutive timestamps, each with ≥ m_c objects, consecutive
Hausdorff distance ≤ δ and lifetime ≥ k_c. The sweep keeps open candidates; a candidate extends to
every cluster at the next timestamp within δ (branching allowed); clusters reached by no candidate
start new candidates (set R), so every output crowd is closed on both ends. Crowds whose cluster set
is contained in another crowd are dropped.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from src.mining.hausdorff import bbox_lower_bound, hausdorff
from src.mining.snapshot import Cluster

MAX_CANDIDATES = 5000  # safety valve against pathological branching


@dataclass
class Link:
    a: int
    b: int
    dH: float | None  # None = pruned by the bbox lower bound (then d_H > δ for sure)
    lb: float
    close: bool


def discover_crowds(clusters: list[Cluster], m_c: int, k_c: int, delta: float, dt: int = 10
                    ) -> tuple[list[list[int]], list[Link]]:
    by_t: dict[int, list[Cluster]] = defaultdict(list)
    for c in clusters:
        by_t[c.t].append(c)
    times = sorted(by_t)
    links: list[Link] = []
    near: dict[int, list[int]] = defaultdict(list)
    for t in times:
        nxt = by_t.get(t + dt, [])
        for a in by_t[t]:
            for b in nxt:
                lb = bbox_lower_bound(a.bbox, b.bbox)
                if lb > delta:
                    links.append(Link(a.id, b.id, None, lb, False))
                    continue
                d = hausdorff(a.pts, b.pts)
                links.append(Link(a.id, b.id, d, lb, d <= delta))
                if d <= delta:
                    near[a.id].append(b.id)
    size = {c.id: c.size for c in clusters}
    closed: list[list[int]] = []
    V: list[list[int]] = []
    prev_t = None
    for t in times:
        if prev_t is not None and t != prev_t + dt:  # gap in time: nothing can be extended
            closed.extend(cr for cr in V if len(cr) >= k_c)
            V = []
        R: set[int] = set()
        nxt_V: list[list[int]] = []
        here = {c.id for c in by_t[t]}
        for cr in V:
            cp = [b for b in near.get(cr[-1], []) if b in here]
            R.update(cp)
            ext = [b for b in cp if size[b] >= m_c]
            if not ext:
                if len(cr) >= k_c:
                    closed.append(cr)
            else:
                nxt_V.extend(cr + [b] for b in ext)
        nxt_V.extend([c.id] for c in by_t[t] if c.id not in R and c.size >= m_c)
        V = nxt_V[:MAX_CANDIDATES]
        prev_t = t
    closed.extend(cr for cr in V if len(cr) >= k_c)
    return drop_contained(closed), links


def drop_contained(seqs: list[list[int]]) -> list[list[int]]:
    """Remove sequences whose cluster set is a subset of another's (keeps the first of equal ones)."""
    seqs = sorted({tuple(s) for s in seqs}, key=lambda s: (-len(s), s))
    kept: list[tuple[int, ...]] = []
    sets: list[set[int]] = []
    for s in seqs:
        ss = set(s)
        if not any(ss <= k for k in sets):
            kept.append(s)
            sets.append(ss)
    return sorted((list(s) for s in kept), key=lambda s: (s[0], len(s)))
