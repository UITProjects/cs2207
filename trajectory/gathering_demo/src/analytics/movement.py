"""Team movement in one match, from trajectories only: squad-centre tracks and a per-team route summary."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.analytics.gazetteer import nearest_place

MAX_FOCUS = 4


def team_tracks(pos: pd.DataFrame) -> pd.DataFrame:
    """Per (team, t): centre of the members present. Columns team, t, x, y, n_alive, in_vehicle, phase."""
    agg = dict(x=("x", "mean"), y=("y", "mean"), n_alive=("player", "nunique"))
    if "in_vehicle" in pos:
        agg["in_vehicle"] = ("in_vehicle", "mean")
    if "phase" in pos:
        agg["phase"] = ("phase", "max")
    out = pos.groupby(["team", "t"], as_index=False).agg(**agg)
    if "in_vehicle" not in out:
        out["in_vehicle"] = 0.0
    if "phase" not in out:
        out["phase"] = 0
    return out.sort_values(["team", "t"]).reset_index(drop=True)


def _route(tr: pd.DataFrame) -> list[tuple[int, str]]:
    """Place of the team centre at the first step of each phase, consecutive repeats dropped."""
    out: list[tuple[int, str]] = []
    for ph, g in tr.groupby("phase", sort=True):
        r = g.iloc[0]
        name = nearest_place(r.x, r.y)
        if not out or out[-1][1] != name:
            out.append((int(ph), name))
    return out


def team_summary(tables: dict, gathering_df: pd.DataFrame | None) -> pd.DataFrame:
    """One row per team: start (landing), route by phase, end of trajectory, distance, vehicle share, gatherings."""
    tracks = team_tracks(tables["positions"])
    n_g: dict[str, int] = {}
    if gathering_df is not None and len(gathering_df):
        for teams in gathering_df["teams"]:
            for tm in teams:
                n_g[tm] = n_g.get(tm, 0) + 1
    rows = []
    for team, tr in tracks.groupby("team"):
        first, last = tr.iloc[0], tr.iloc[-1]
        step = np.hypot(np.diff(tr["x"]), np.diff(tr["y"]))
        route = _route(tr)
        rows.append(dict(
            team=team, land_t=float(first.t), land_place=nearest_place(first.x, first.y),
            route=route, route_str=" → ".join(f"{p} (P{ph})" if i else p for i, (ph, p) in enumerate(route)),
            end_t=float(last.t), end_place=nearest_place(last.x, last.y), dist_km=float(step.sum() / 1000),
            vehicle_pct=float(100 * tr["in_vehicle"].mean()), n_gatherings=n_g.get(team, 0)))
    return pd.DataFrame(rows).sort_values("team").reset_index(drop=True)


def default_focus(summary: pd.DataFrame, n: int = 3) -> list[str]:
    """The n teams that took part in the most gatherings (ties → team id)."""
    if summary.empty:
        return []
    s = summary.sort_values(["n_gatherings", "team"], ascending=[False, True])
    return list(s["team"][: min(n, MAX_FOCUS)])
