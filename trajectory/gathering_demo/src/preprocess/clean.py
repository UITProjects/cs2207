"""Parsed tables → mining-ready tables on a Δt grid (data/processed/{source}/{match_id}/).

* landing cut (LogParachuteLanding; fallback: first sample below 200 m altitude),
* death cut (LogPlayerKillV2 victim time; else last sample),
* outlier jumps (> max_speed_foot m/s while not in a vehicle) dropped,
* resample to the Δt grid with linear interpolation for gaps ≤ max_gap_s only (never fabricate),
* phase = number of changes of the white circle (`warn_r`) so far; phase 0 = before the first zone.

    uv run python -m src.preprocess.clean --all [--source mock]
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import datasource_name, load_config, path
from src.parse.telemetry import read_tables, write_tables

log = logging.getLogger("clean")


def label_phases(zones: pd.DataFrame) -> pd.DataFrame:
    """phase += 1 each time the white circle radius changes (rounded to 1 m); 0 before the first zone."""
    z = zones.sort_values("t").reset_index(drop=True).copy()
    r = z["warn_r"].round(0).to_numpy()
    first = r[0] if len(r) else 0
    phase, cur, out = 0, first, []
    for v in r:
        if v != cur:
            phase += 1
            cur = v
        out.append(phase)
    z["phase"] = out
    return z


def phase_at(zones: pd.DataFrame, t: np.ndarray) -> np.ndarray:
    if zones.empty:
        return np.zeros(len(t), int)
    idx = np.searchsorted(zones["t"].to_numpy(), t, side="right") - 1
    return np.where(idx < 0, 0, zones["phase"].to_numpy()[np.clip(idx, 0, None)])


def drop_outliers(g: pd.DataFrame, vmax: float) -> pd.DataFrame:
    keep = np.ones(len(g), bool)
    xs, ys, ts, veh = g["x"].to_numpy(), g["y"].to_numpy(), g["t"].to_numpy(), g["in_vehicle"].to_numpy()
    last = 0
    for i in range(1, len(g)):
        dtt = max(ts[i] - ts[last], 1e-3)
        v = np.hypot(xs[i] - xs[last], ys[i] - ys[last]) / dtt
        if v > vmax and not (veh[i] or veh[last]):
            keep[i] = False
        else:
            last = i
    return g[keep]


def resample(g: pd.DataFrame, dt: float, max_gap: float) -> pd.DataFrame:
    ts = g["t"].to_numpy()
    if len(ts) == 0:
        return g.iloc[0:0]
    grid = np.arange(np.ceil(ts[0] / dt) * dt, np.floor(ts[-1] / dt) * dt + 1e-9, dt)
    if len(grid) == 0:
        return g.iloc[0:0]
    j = np.clip(np.searchsorted(ts, grid, side="right") - 1, 0, len(ts) - 1)  # last sample ≤ grid
    k = np.clip(j + 1, 0, len(ts) - 1)
    exact = np.isclose(ts[j], grid)
    gap = ts[k] - ts[j]
    ok = exact | ((gap <= max_gap) & (k > j))
    f = np.where(gap > 0, (grid - ts[j]) / np.where(gap > 0, gap, 1), 0.0)
    f = np.where(exact, 0.0, f)
    out = pd.DataFrame({
        "t": grid.round().astype(int),
        "x": g["x"].to_numpy()[j] + f * (g["x"].to_numpy()[k] - g["x"].to_numpy()[j]),
        "y": g["y"].to_numpy()[j] + f * (g["y"].to_numpy()[k] - g["y"].to_numpy()[j]),
        "in_vehicle": g["in_vehicle"].to_numpy()[j],
    })[ok]
    return out


def clean_match(tables: dict, dt: float = 10, max_gap: float = 30, vmax: float = 60) -> dict:
    pos = tables["positions"]
    mid = tables["meta"]["match_id"]
    land = dict(zip(tables["landings"]["player"], tables["landings"]["t_land"], strict=True))
    death = tables["kills"].groupby("victim")["t"].min().to_dict()
    zones = label_phases(tables["zones"])
    parts = []
    for (player, team), g in pos.groupby(["player", "team"], sort=True):
        g = g.sort_values("t")
        tl = land.get(player)
        if tl is None:  # fallback: first sample below 200 m
            low = g[g["z"] < 200]
            tl = low["t"].iloc[0] if len(low) else g["t"].iloc[-1] + 1
        g = g[(g["t"] >= tl) & (g["t"] <= death.get(player, np.inf))]
        g = drop_outliers(g, vmax)
        r = resample(g, dt, max_gap)
        if len(r):
            r.insert(0, "team", team)
            r.insert(0, "player", player)
            parts.append(r)
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["player", "team", "t", "x", "y"])
    out = out.sort_values(["t", "player"]).reset_index(drop=True)
    out["phase"] = phase_at(zones, out["t"].to_numpy().astype(float))
    out.insert(0, "match_id", mid)
    kills = tables["kills"].copy()
    kills["phase"] = phase_at(zones, kills["t"].to_numpy())
    meta = dict(tables["meta"], dt=dt, n_points=len(out), t_max=int(out["t"].max()) if len(out) else 0,
                n_phases=int(zones["phase"].max()) if len(zones) else 0)
    return dict(positions=out, zones=zones, kills=kills, results=tables["results"], landings=tables["landings"],
                meta=meta)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--source", default=None)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_config()["preprocess"]
    src = a.source or datasource_name()
    n = 0
    dirs = sorted(p for p in (path("interim") / src).iterdir() if (p / "meta.json").exists())
    for d in dirs:
        out: Path = path("processed") / src / d.name
        if (out / "meta.json").exists() and not a.force:
            continue
        write_tables(clean_match(read_tables(d), cfg["dt"], cfg["max_gap_s"], cfg["max_speed_foot"]), out)
        n += 1
    log.info("cleaned %d matches (%d already done) -> %s", n, len(dirs) - n, path("processed") / src)


if __name__ == "__main__":
    main()
