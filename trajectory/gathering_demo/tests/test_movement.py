"""Team movement analytics on a tiny synthetic match with known answers."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.analytics.movement import default_focus, team_summary, team_tracks


def _match() -> dict:
    rows = []
    # T01: 2 players walking east along y=1000 for 6 steps, x = 1000 + 100·i, offset ±10 in y
    for i in range(6):
        for p, dy in (("P001", -10), ("P002", 10)):
            rows.append(dict(player=p, team="T01", t=10 * i, x=1000 + 100 * i, y=1000 + dy, in_vehicle=False,
                             phase=0 if i < 3 else 1))
    # T02: 2 players standing far away; P004's trajectory ends after t=20 (no rows afterwards)
    for i in range(6):
        rows.append(dict(player="P003", team="T02", t=10 * i, x=7000, y=7000, in_vehicle=False,
                         phase=0 if i < 3 else 1))
        if i <= 2:
            rows.append(dict(player="P004", team="T02", t=10 * i, x=7100, y=7000, in_vehicle=False,
                             phase=0 if i < 3 else 1))
    return dict(positions=pd.DataFrame(rows))


def test_tracks_are_mean_of_alive_members():
    tb = _match()
    tr = team_tracks(tb["positions"]).set_index(["team", "t"])
    assert np.isclose(tr.loc[("T01", 20), "x"], 1200) and np.isclose(tr.loc[("T01", 20), "y"], 1000)
    assert tr.loc[("T02", 10), "n_alive"] == 2 and np.isclose(tr.loc[("T02", 10), "x"], 7050)
    assert tr.loc[("T02", 40), "n_alive"] == 1 and np.isclose(tr.loc[("T02", 40), "x"], 7000)


def test_summary_route_end_and_distance():
    tb = _match()
    s = team_summary(tb, None).set_index("team")
    assert s.loc["T01", "land_t"] == 0 and s.loc["T01", "end_t"] == 50
    assert s.loc["T02", "end_t"] == 50  # P003 keeps moving (well, standing) until t = 50
    assert np.isclose(s.loc["T01", "dist_km"], 0.5)
    assert [ph for ph, _ in s.loc["T01", "route"]][0] == 0
    assert "rank" not in s.columns and "survived" not in s.columns


def test_default_focus_by_gatherings():
    tb = _match()
    g = pd.DataFrame(dict(teams=[["T02"], ["T02", "T01"], ["T02"]]))
    s = team_summary(tb, g)
    assert dict(zip(s["team"], s["n_gatherings"], strict=True)) == {"T01": 1, "T02": 3}
    assert default_focus(s, n=2) == ["T02", "T01"]
