"""Team report for VOD review: moments a team was inside a gathering and what happened next."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.viz.map_plot import fmt_t

WINDOW = 120.0


def team_report(tables: dict, res, gdf: pd.DataFrame, team: str) -> pd.DataFrame:
    pos = tables["positions"]
    members = sorted(pos.loc[pos["team"] == team, "player"].unique())
    death = tables["kills"].groupby("victim")["t"].min().to_dict()
    kills = tables["kills"]
    rows = []
    for g in gdf.itertuples() if not gdf.empty else []:
        present = sorted({m for cid in g.clusters for m in res.clusters[cid].members if m in members})
        if not present:
            continue
        par = sorted(set(g.participators) & set(members))
        lost = [m for m in members if g.t_start <= death.get(m, np.inf) <= g.t_end + WINDOW]
        where = []
        for m in lost:
            k = kills[kills["victim"] == m].iloc[0]
            where.append(f"{m} @ {fmt_t(k.t)}")
        alive_after = [m for m in members if death.get(m, np.inf) > g.t_end + WINDOW]
        outcome = ("bị loại cả đội" if not alive_after else ("mất người" if lost else "an toàn"))
        rows.append(dict(vod_start=fmt_t(g.t_start), vod_end=fmt_t(g.t_end), t_start=int(g.t_start), t_end=int(g.t_end),
                         phase=int(g.phase), place=g.place, gathering=f"G{g.id + 1}", zone=g.zone_label,
                         members_present=", ".join(present), participators=", ".join(par) or "—",
                         outcome=outcome, eliminated=", ".join(where) or "—"))
    return pd.DataFrame(rows)
