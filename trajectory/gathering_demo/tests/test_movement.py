"""Team movement analytics on a tiny synthetic match with known answers."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.analytics.movement import default_focus, team_summary, team_tracks, zone_gap


def _match() -> dict:
    rows = []
    # T01: 2 players walking east along y=1000 for 6 steps, x = 1000 + 100·i, offset ±10 in y
    for i in range(6):
        for p, dy in (("P001", -10), ("P002", 10)):
            rows.append(dict(player=p, team="T01", t=10 * i, x=1000 + 100 * i, y=1000 + dy, in_vehicle=False,
                             phase=0 if i < 3 else 1))
    # T02: 2 players standing far away; P004 dies after t=20 (no rows afterwards)
    for i in range(6):
        rows.append(dict(player="P003", team="T02", t=10 * i, x=7000, y=7000, in_vehicle=False,
                         phase=0 if i < 3 else 1))
        if i <= 2:
            rows.append(dict(player="P004", team="T02", t=10 * i, x=7100, y=7000, in_vehicle=False,
                             phase=0 if i < 3 else 1))
    pos = pd.DataFrame(rows)
    kills = pd.DataFrame([dict(t=25, killer="P001", victim="P004", killer_team="T01", victim_team="T02", x=7100,
                               y=7000, phase=0),
                          dict(t=55, killer="P001", victim="P003", killer_team="T01", victim_team="T02", x=7000,
                               y=7000, phase=1)])
    zones = pd.DataFrame(dict(t=[0.0, 30.0], safe_x=[1000.0, 1000.0], safe_y=[1000.0, 1000.0],
                              safe_r=[5000.0, 300.0], warn_x=[1000.0, 1000.0], warn_y=[1000.0, 1000.0],
                              warn_r=[5000.0, 300.0], phase=[0, 1]))
    results = pd.DataFrame(dict(team=["T01", "T02"], ranking=[1, 2]))
    return dict(positions=pos, kills=kills, zones=zones, results=results)


def test_tracks_are_mean_of_alive_members():
    tb = _match()
    tr = team_tracks(tb["positions"]).set_index(["team", "t"])
    assert np.isclose(tr.loc[("T01", 20), "x"], 1200) and np.isclose(tr.loc[("T01", 20), "y"], 1000)
    assert tr.loc[("T02", 10), "n_alive"] == 2 and np.isclose(tr.loc[("T02", 10), "x"], 7050)
    assert tr.loc[("T02", 40), "n_alive"] == 1 and np.isclose(tr.loc[("T02", 40), "x"], 7000)


def test_zone_gap_sign():
    tb = _match()
    tr = team_tracks(tb["positions"])
    gap = zone_gap(tr, tb["zones"])
    t01 = dict(zip(tr.loc[tr["team"] == "T01", "t"], gap[tr["team"] == "T01"], strict=True))
    assert t01[0] < 0 and t01[20] < 0  # big phase-0 circle
    assert np.isclose(t01[50], 200)  # x = 1500, centre 1000, r = 300 → 200 m outside
    t02_late = gap[(tr["team"] == "T02") & (tr["t"] >= 30)].to_numpy()
    assert (t02_late > 0).all()  # far away from the small circle → outside


def test_summary_elimination_and_route():
    tb = _match()
    s = team_summary(tb, None).set_index("team")
    assert s.loc["T01", "survived"] and s.loc["T01", "rank"] == 1
    assert not s.loc["T02", "survived"] and s.loc["T02", "out_t"] == 55
    assert np.isclose(s.loc["T01", "dist_km"], 0.5)
    assert s.loc["T02", "outside_s"] == 60  # (7000, 7000) is 8.5 km from the centre: outside at every step
    assert default_focus(s.reset_index(), n=2) == ["T01", "T02"]
