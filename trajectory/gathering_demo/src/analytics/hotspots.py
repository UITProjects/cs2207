"""Multi-match hotspots: gatherings counted on a 200 m grid per phase, and top places per phase."""
from __future__ import annotations

import numpy as np
import pandas as pd

CELL = 200.0


def grid_counts(g: pd.DataFrame, cell: float = CELL) -> pd.DataFrame:
    if g.empty:
        return pd.DataFrame(columns=["phase", "gx", "gy", "x", "y", "count", "matches"])
    d = g.assign(gx=np.floor(g["cx"] / cell).astype(int), gy=np.floor(g["cy"] / cell).astype(int))
    out = d.groupby(["phase", "gx", "gy"]).agg(count=("match_id", "size"), matches=("match_id", "nunique")).reset_index()
    out["x"], out["y"] = (out["gx"] + 0.5) * cell, (out["gy"] + 0.5) * cell
    return out


def top_places(g: pd.DataFrame, n_matches: int, top: int = 10) -> pd.DataFrame:
    """place × phase: number of gatherings, % of matches with ≥ 1, median start after zone, mean size."""
    if g.empty:
        return pd.DataFrame()
    out = g.groupby(["place", "phase"]).agg(gatherings=("match_id", "size"), matches=("match_id", "nunique"),
                                            participators=("n_participators", "mean"),
                                            t_after_zone=("t_after_zone", "median"),
                                            forced=("forced", "mean")).reset_index()
    out["pct_matches"] = 100 * out["matches"] / max(n_matches, 1)
    return out.sort_values(["gatherings", "pct_matches"], ascending=False).head(top).reset_index(drop=True)
