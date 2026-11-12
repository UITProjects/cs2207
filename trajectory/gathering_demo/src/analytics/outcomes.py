"""Gathering ↔ outcomes. Always reported with sample sizes; correlation ≠ causation.

1. `exposure_rows`: for each gathering, every player alive at its start is either a participator
   (exposed) or a baseline player (alive, same match, same time window, not a participator of any
   gathering overlapping the window). Outcome: eliminated within [t_start, t_end + 120 s].
   The same is done for teams (team wiped in the window).
2. `team_participation`: per (match, team) number of gatherings participated (overall and per
   phase) + final ranking.
3. `kill_inout`: eliminations whose victim stood inside a gathering's hull (cluster at that step)
   vs outside, normalised by player-time inside vs outside (kills per player-minute).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from shapely.geometry import MultiPoint, Point

WINDOW = 120.0


def _deaths(tables: dict) -> tuple[dict[str, float], dict[str, float], dict[str, str]]:
    pos = tables["positions"]
    team_of = dict(zip(pos["player"], pos["team"], strict=False))
    death = tables["kills"].groupby("victim")["t"].min().to_dict()
    tw: dict[str, float] = {}
    for tm, g in pos.groupby("team"):
        ds = [death.get(p, np.inf) for p in g["player"].unique()]
        tw[tm] = max(ds)
    return death, tw, team_of


def exposure_rows(tables: dict, res, gdf: pd.DataFrame) -> pd.DataFrame:
    if gdf.empty:
        return pd.DataFrame()
    pos = tables["positions"]
    mid = tables["meta"]["match_id"]
    death, team_wipe, team_of = _deaths(tables)
    rows = []
    for r in gdf.itertuples():
        w0, w1 = r.t_start, r.t_end + WINDOW
        overl = gdf[(gdf["t_start"] <= w1) & (gdf["t_end"] >= w0)]
        busy = {p for ps in overl["participators"] for p in ps}
        alive = pos.loc[pos["t"] == r.t_start, "player"].unique()
        par = set(r.participators)
        for p in alive:
            if p not in par and p in busy:
                continue
            grp = "participator" if p in par else "baseline"
            rows.append(dict(match_id=mid, gid=r.id, phase=r.phase, place=r.place, level="player", unit=p, group=grp,
                             eliminated=bool(w0 <= death.get(p, np.inf) <= w1)))
        teams_par = {team_of[p] for p in par}
        busy_t = {team_of[p] for p in busy}
        for tm in {team_of[p] for p in alive}:
            if tm not in teams_par and tm in busy_t:
                continue
            grp = "participator" if tm in teams_par else "baseline"
            rows.append(dict(match_id=mid, gid=r.id, phase=r.phase, place=r.place, level="team", unit=tm, group=grp,
                             eliminated=bool(w0 <= team_wipe.get(tm, np.inf) <= w1)))
    return pd.DataFrame(rows)


def team_participation(tables: dict, gdf: pd.DataFrame) -> pd.DataFrame:
    res = tables["results"]
    mid = tables["meta"]["match_id"]
    rows = []
    for tm, rk in zip(res["team"], res["ranking"], strict=True):
        if gdf.empty:
            per = {}
        else:
            mask = gdf["teams"].apply(lambda ts, tm=tm: tm in ts)
            per = gdf[mask].groupby("phase").size().to_dict()
        rows.append(dict(match_id=mid, team=tm, ranking=int(rk), n_gatherings=int(sum(per.values())),
                         **{f"ph{p}": int(per.get(p, 0)) for p in range(0, 9)}))
    return pd.DataFrame(rows)


def kill_inout(tables: dict, res, gdf: pd.DataFrame) -> dict:
    """Kills inside gathering hulls vs outside, with player-minutes of exposure (Δt steps)."""
    dt = float(tables["meta"].get("dt", 10))
    pos = tables["positions"]
    kills = tables["kills"]
    hulls: dict[int, list] = {}
    inside_steps = 0
    for g in gdf.itertuples() if not gdf.empty else []:
        for cid in g.clusters:
            c = res.clusters[cid]
            hulls.setdefault(c.t, []).append(MultiPoint([tuple(p) for p in c.pts]).convex_hull.buffer(25))
            inside_steps += c.size
    total_steps = len(pos)
    k_in = 0
    for k in kills.itertuples():
        step = int(np.floor(k.t / dt) * dt)
        if any(h.contains(Point(k.x, k.y)) for h in hulls.get(step, [])):
            k_in += 1
    return dict(match_id=tables["meta"]["match_id"], kills_inside=k_in, kills_outside=len(kills) - k_in,
                pmin_inside=inside_steps * dt / 60, pmin_outside=(total_steps - inside_steps) * dt / 60)


def rate_table(exp: pd.DataFrame, level: str = "player", by: str = "phase") -> pd.DataFrame:
    """Elimination rate within the window: participators vs baseline, with n."""
    if exp.empty:
        return pd.DataFrame()
    e = exp[exp["level"] == level]
    t = e.groupby([by, "group"])["eliminated"].agg(["mean", "size"]).unstack("group")
    t.columns = [f"{a}_{b}" for a, b in t.columns]
    return t.reset_index().rename(columns={"mean_participator": "rate_participator", "mean_baseline": "rate_baseline",
                                           "size_participator": "n_participator", "size_baseline": "n_baseline"})
