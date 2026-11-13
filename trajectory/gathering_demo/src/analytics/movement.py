"""Team movement in one match: squad-centre tracks, rotation summary, distance to the zone edge."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.analytics.gazetteer import nearest_place

MAX_FOCUS = 4


def team_tracks(pos: pd.DataFrame) -> pd.DataFrame:
    """Per (team, t): centre of the alive, landed members. Columns team, t, x, y, n_alive, in_vehicle, phase."""
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


def _zone_index(zones: pd.DataFrame, t: np.ndarray) -> np.ndarray:
    return np.clip(np.searchsorted(zones["t"].to_numpy(), t, side="right") - 1, 0, len(zones) - 1)


def zone_gap(tracks: pd.DataFrame, zones: pd.DataFrame | None) -> pd.Series:
    """Distance (m) from the team centre to the edge of the current safe circle; < 0 means inside."""
    if zones is None or zones.empty:
        return pd.Series(np.nan, index=tracks.index)
    z = zones.iloc[_zone_index(zones, tracks["t"].to_numpy())]
    d = np.hypot(tracks["x"].to_numpy() - z["safe_x"].to_numpy(), tracks["y"].to_numpy() - z["safe_y"].to_numpy())
    return pd.Series(d - z["safe_r"].to_numpy(), index=tracks.index)


def _route(tr: pd.DataFrame) -> list[tuple[int, str]]:
    """Place of the team centre at the first step of each phase, consecutive repeats dropped."""
    out: list[tuple[int, str]] = []
    for ph, g in tr.groupby("phase", sort=True):
        r = g.iloc[0]
        name = nearest_place(r.x, r.y)
        if not out or out[-1][1] != name:
            out.append((int(ph), name))
    return out


def team_summary(tables: dict, gathering_df: pd.DataFrame | None, dt: int = 10) -> pd.DataFrame:
    """One row per team: rank, landing, route by phase, elimination, distance, vehicle share, gatherings."""
    pos, kills = tables["positions"], tables["kills"]
    rank = dict(zip(tables["results"]["team"], tables["results"]["ranking"], strict=False))
    tracks = team_tracks(pos)
    tracks["gap"] = zone_gap(tracks, tables.get("zones"))
    n_g: dict[str, int] = {}
    if gathering_df is not None and len(gathering_df):
        for teams in gathering_df["teams"]:
            for tm in teams:
                n_g[tm] = n_g.get(tm, 0) + 1
    size = pos.groupby("team")["player"].nunique().to_dict()
    rows = []
    for team, tr in tracks.groupby("team"):
        first, last = tr.iloc[0], tr.iloc[-1]
        step = np.hypot(np.diff(tr["x"]), np.diff(tr["y"]))
        tk = kills[kills["victim_team"] == team].sort_values("t")
        wiped = len(tk) >= size.get(team, 4) and rank.get(team) != 1
        if wiped:
            k = tk.iloc[-1]
            out_t, out_place = float(k.t), nearest_place(k.x, k.y)
        else:
            out_t, out_place = float(last.t), nearest_place(last.x, last.y)
        route = _route(tr)
        rows.append(dict(
            team=team, rank=int(rank.get(team, 0)), land_t=float(first.t), land_place=nearest_place(first.x, first.y),
            route=route, route_str=" → ".join(f"{p} (P{ph})" if i else p for i, (ph, p) in enumerate(route)),
            out_t=out_t, out_place=out_place, survived=not wiped, kills_taken=len(tk),
            kills_made=int((kills["killer_team"] == team).sum()) if "killer_team" in kills else 0,
            dist_km=float(step.sum() / 1000), vehicle_pct=float(100 * tr["in_vehicle"].mean()),
            n_gatherings=n_g.get(team, 0), outside_s=float((tr["gap"] > 0).sum() * dt)))
    return pd.DataFrame(rows).sort_values("rank").reset_index(drop=True)


def default_focus(summary: pd.DataFrame, n: int = 3) -> list[str]:
    """Winner first, then the teams that took part in the most gatherings (ties → better rank)."""
    if summary.empty:
        return []
    s = summary.sort_values("rank")
    out = [s.iloc[0]["team"]]
    rest = s.iloc[1:].sort_values(["n_gatherings", "rank"], ascending=[False, True])
    out += list(rest["team"][: max(n - 1, 0)])
    return out[:MAX_FOCUS]
