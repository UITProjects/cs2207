"""Zone control: where a gathering sits relative to the white circle (next safe zone) when it forms.

label: 'center' (centroid within 50% of the white radius), 'edge' (50–110%), 'outside' (> 110%),
'no zone' (phase 0). forced = phase ≥ 6 (late game: everyone is squeezed) or 'edge' (pushed by the
zone); everything else is 'chosen' (hot drops, chokepoints, camps).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def zone_row(zones: pd.DataFrame, t: float) -> pd.Series | None:
    if zones is None or zones.empty:
        return None
    i = max(int(np.searchsorted(zones["t"].to_numpy(), t, side="right")) - 1, 0)
    return zones.iloc[i]


def phase_starts(zones: pd.DataFrame) -> dict[int, float]:
    return zones.groupby("phase")["t"].min().to_dict() if len(zones) else {0: 0.0}


def annotate_zone(gdf: pd.DataFrame, zones: pd.DataFrame) -> pd.DataFrame:
    g = gdf.copy()
    if g.empty:
        for c in ("zone_label", "forced", "zone_rel", "t_after_zone"):
            g[c] = pd.Series(dtype=object)
        return g
    starts = phase_starts(zones)
    labels, rel, forced, after = [], [], [], []
    for r in g.itertuples():
        z = zone_row(zones, r.t_start)
        ph = int(r.phase)
        if z is None or ph == 0:
            lab, rr = "no zone", np.nan
        else:
            rr = float(np.hypot(r.cx - z.warn_x, r.cy - z.warn_y) / max(z.warn_r, 1.0))
            lab = "center" if rr < 0.5 else ("edge" if rr <= 1.1 else "outside")
        labels.append(lab)
        rel.append(rr)
        forced.append(bool(ph >= 6 or lab == "edge"))
        after.append(float(r.t_start - starts.get(ph, 0.0)))
    g["zone_label"], g["zone_rel"], g["forced"], g["t_after_zone"] = labels, rel, forced, after
    return g
