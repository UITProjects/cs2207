"""Synthetic mining tests with known answers (CLAUDE.md §8 cases a–d) + margin checks
(the result must not change under small parameter moves, as legacy/check_core.py did)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.mining.crowd import discover_crowds
from src.mining.hausdorff import bbox_lower_bound, hausdorff
from src.mining.pipeline import run_pipeline
from src.mining.snapshot import snapshot_clusters

P = dict(eps=150, min_pts=3, m_c=8, delta=300, k_c=6, k_p=4, m_p=6)
DT = 10


def frame(rows):
    df = pd.DataFrame(rows, columns=["player", "t", "x", "y"])
    df["team"] = "T" + (df["player"].str[1:].astype(int) // 4 + 1).astype(str).str.zfill(2)
    return dict(positions=df, meta=dict(dt=DT))


def group(rng, ids, steps, center, spread=30.0, drift=(0.0, 0.0), t0=0):
    rows = []
    for s in range(steps):
        cx, cy = center[0] + drift[0] * s, center[1] + drift[1] * s
        for o in ids:
            rows.append((f"P{o:03d}", t0 + s * DT, cx + rng.normal(0, spread), cy + rng.normal(0, spread)))
    return rows


def test_hausdorff_and_lower_bound():
    A = np.array([[0.0, 0], [10, 0]])
    B = np.array([[0.0, 0], [40, 0]])
    assert hausdorff(A, B) == pytest.approx(30)
    rng = np.random.default_rng(0)
    for _ in range(200):
        X, Y = rng.uniform(0, 500, (8, 2)), rng.uniform(0, 500, (5, 2)) + rng.uniform(-300, 300, 2)
        bx = lambda Z: (*Z.min(0), *Z.max(0))  # noqa: E731
        assert bbox_lower_bound(bx(X), bx(Y)) <= hausdorff(X, Y) + 1e-9


def test_a_static_group_is_one_gathering():
    rng = np.random.default_rng(1)
    r = run_pipeline(frame(group(rng, range(1, 13), 12, (1000, 1000))), P)  # 12 players, 2 minutes
    assert len(r.crowds) == 1 and len(r.gatherings) == 1
    g, par, _ = r.gatherings[0]
    assert len(g) == 12 and len(par) == 12


def test_b_changing_members_is_crowd_but_not_gathering():
    rng = np.random.default_rng(2)
    rows = []
    for s in range(12):  # 10 brand-new players at every step at the same place
        rows += group(rng, range(100 + 10 * s, 110 + 10 * s), 1, (2000, 2000), t0=s * DT)
    r = run_pipeline(frame(rows), P)
    assert len(r.crowds) == 1 and len(r.crowds[0]) == 12
    assert r.gatherings == []


def test_c_two_far_groups_are_two_crowds():
    rng = np.random.default_rng(3)
    rows = group(rng, range(1, 11), 10, (1000, 1000)) + group(rng, range(11, 21), 10, (1000 + 2000, 1000))
    r = run_pipeline(frame(rows), P)
    assert len(r.crowds) == 2 and len(r.gatherings) == 2
    assert {tuple(sorted(par))[0] for _, par, _ in r.gatherings} == {"P001", "P011"}


def test_d_slowly_moving_group_is_one_continuous_crowd():
    rng = np.random.default_rng(4)
    r = run_pipeline(frame(group(rng, range(1, 11), 20, (500, 500), drift=(60, 40))), P)  # ~72 m per step < δ
    assert len(r.crowds) == 1 and len(r.crowds[0]) == 20 and len(r.gatherings) == 1


def test_fast_group_breaks_crowd():
    rng = np.random.default_rng(5)
    r = run_pipeline(frame(group(rng, range(1, 11), 10, (500, 500), spread=10, drift=(400, 0))), P)
    assert r.crowds == []  # each step jumps 400 m > δ


def test_divide_drops_short_visitors():
    """10 regulars, but at steps 5–6 nine strangers stand there instead: one 12-step crowd. TAD cuts
    the stranger steps → two 5-step halves: below k_c=6 → no gathering; with k_c=4 both are gatherings."""
    rng = np.random.default_rng(6)
    rows = []
    for s in range(12):
        ids = range(200, 209) if s in (5, 6) else range(1, 11)
        rows += group(rng, ids, 1, (800, 800), t0=s * DT)
    r = run_pipeline(frame(rows), P)
    assert len(r.crowds) == 1 and r.gatherings == []
    r4 = run_pipeline(frame(rows), dict(P, k_c=4, k_p=3))
    assert [len(g) for g, _, _ in r4.gatherings] == [5, 5]


def test_closed_crowd_not_extendable():
    rng = np.random.default_rng(7)
    rows = group(rng, range(1, 11), 8, (1000, 1000)) + group(rng, range(1, 4), 3, (1000, 1000), t0=80)
    clusters, _ = snapshot_clusters(frame(rows)["positions"], 150, 3)
    crowds, _ = discover_crowds(clusters, 8, 6, 300)
    assert len(crowds) == 1 and len(crowds[0]) == 8  # the 3-person tail is below m_c


@pytest.mark.parametrize("key,vals", [("eps", [140, 160]), ("delta", [280, 320]), ("m_p", [5, 7])])
def test_margins(key, vals):
    rng = np.random.default_rng(8)
    rows = group(rng, range(1, 13), 12, (1000, 1000)) + group(rng, range(20, 30), 10, (4000, 1000), drift=(60, 0))
    base = run_pipeline(frame(rows), P)
    shape = lambda r: ([len(c) for c in r.crowds], [len(g) for g, _, _ in r.gatherings])  # noqa: E731
    for v in vals:
        assert shape(run_pipeline(frame(rows), dict(P, **{key: v}))) == shape(base)
