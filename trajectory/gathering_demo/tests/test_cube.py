"""3D space-time cube: map floor, disc merging, algorithm/team cubes on the committed sample match."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.analytics.gazetteer import nearest_place
from src.analytics.movement import default_focus, team_summary, team_tracks
from src.config import default_params, path
from src.mining.pipeline import run_pipeline
from src.parse.telemetry import read_tables
from src.viz.cube import (
    FULL,
    N_COLORS,
    algo_cube,
    crowd_window,
    map_floor,
    space_time_cube,
    team_cube,
    team_palette,
    window_teams,
)
from src.viz.map_plot import FOCUS_COLORS


def test_map_floor_surface():
    s = map_floor(FULL, 0.0, res=64)
    assert np.asarray(s.surfacecolor).shape == (64, 64) and np.asarray(s.z).shape == (64, 64)
    stops = [st[0] for st in s.colorscale]
    assert stops[0] == 0 and stops[-1] == 1 and all(a <= b for a, b in zip(stops, stops[1:], strict=False))
    sc = np.asarray(s.surfacecolor)
    assert sc.min() >= 0 and sc.max() <= N_COLORS - 1


def test_discs_merged_per_colour():
    sq = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=float)
    discs = [dict(pts=sq + 10 * i, t=10 * i, color="#f00" if i % 2 else "#00f") for i in range(6)]
    fig = space_time_cube((0, 0, 500, 500), 0, 60, discs=discs, floor=False)
    meshes = [tr for tr in fig.data if tr.type == "mesh3d"]
    assert len(meshes) == 2
    assert sorted(len(m.i) for m in meshes) == [12, 12]  # 3 square discs × 4 fan triangles each


@pytest.fixture(scope="module")
def sample():
    d = next(p for p in sorted((path("sample") / "mock").iterdir()) if (p / "meta.json").exists())
    t = read_tables(Path(d))
    r = run_pipeline(t, default_params())
    for df in (r.crowd_df, r.gathering_df):
        df["place"] = [nearest_place(x, y) for x, y in zip(df["cx"], df["cy"], strict=True)]
    return t, r


@pytest.mark.parametrize("mode", ["raw", "clusters", "crowds", "participators"])
def test_algo_cube_modes(sample, mode):
    t, r = sample
    assert r.crowds, "sample match must have crowds"
    view, lo, hi = crowd_window(r, 0)
    fig = algo_cube(r, t["positions"], mode, view, lo, hi, 0)
    data = [tr for tr in fig.data if tr.type == "scatter3d" and tr.z is not None]
    zs = [z for tr in data for z in tr.z if z is not None]
    assert zs and lo <= min(zs) and max(zs) <= hi
    if mode != "raw":
        assert any(tr.type == "mesh3d" for tr in fig.data)
    if mode == "crowds":
        assert any(tr.type == "scatter3d" and tr.line.dash == "dash" for tr in fig.data)


def test_team_cube_focus_lines(sample):
    t, r = sample
    s = team_summary(t, r.gathering_df)
    focus = default_focus(s)
    colors = dict(zip(focus, FOCUS_COLORS, strict=False))
    fig = team_cube(team_tracks(t["positions"]), s, focus, colors, r.gathering_df, r.clusters, (0, 1700))
    coloured = {tr.line.color for tr in fig.data if tr.type == "scatter3d" and tr.mode == "lines"}
    assert set(colors.values()) <= coloured
    assert isinstance(fig.data[0].z, (np.ndarray, list, tuple, pd.Series)) or fig.data[0].type == "surface"


def _team_lines(fig, colors):
    return [tr for tr in fig.data if tr.type == "scatter3d" and tr.line.color in set(colors.values())]


def test_algo_cube_colours_by_team_and_filters(sample):
    t, r = sample
    view, lo, hi = crowd_window(r, 0)
    wt = window_teams(t["positions"], view, lo, hi)
    colors = team_palette(wt)
    fig = algo_cube(r, t["positions"], "raw", view, lo, hi, 0, colors=colors)
    lines = _team_lines(fig, colors)
    assert len(lines) == len(wt) and len(set(colors.values())) == len(wt)  # one centre line per team
    one = algo_cube(r, t["positions"], "raw", view, lo, hi, 0, colors=colors, teams=[wt[0]])
    only = _team_lines(one, colors)
    assert len(only) == 1 and only[0].line.color == colors[wt[0]]
    per_player = algo_cube(r, t["positions"], "raw", view, lo, hi, 0, colors=colors, by="player")
    assert len(_team_lines(per_player, colors)) == len(wt)  # one trace per team, many players inside


def test_participators_solid_vs_passing(sample):
    t, r = sample
    ci = next(i for i, td in enumerate(r.tads) if td["gatherings"])
    view, lo, hi = crowd_window(r, ci)
    colors = team_palette(window_teams(t["positions"], view, lo, hi))
    fig = algo_cube(r, t["positions"], "participators", view, lo, hi, ci, colors=colors)
    lines = _team_lines(fig, colors)
    solid = [tr for tr in lines if tr.line.dash == "solid"]
    dashed = [tr for tr in lines if tr.line.dash == "dash"]
    assert solid
    assert all("chỉ đi qua" in tr.name for tr in dashed)
    assert all("participator" in tr.name for tr in solid)
