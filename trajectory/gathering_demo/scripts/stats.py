"""Print dataset + mining stats (CLAUDE.md §8): points per match, actual Δt, clusters per timestamp,
crowds / gatherings per match per phase.

    uv run python scripts/stats.py [--source mock] [--n 10]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import datasource_name, default_params, path  # noqa: E402
from src.mining.pipeline import run_pipeline  # noqa: E402
from src.parse.telemetry import read_tables  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=None)
    ap.add_argument("--n", type=int, default=10)
    a = ap.parse_args()
    src = a.source or datasource_name()
    base = path("processed") / src
    if not base.exists():
        base = path("sample") / src
    dirs = sorted(d for d in base.iterdir() if (d / "meta.json").exists())[: a.n]
    rows, ph = [], []
    for d in dirs:
        raw = path("interim") / src / d.name / "positions.parquet"
        dts = np.nan
        if raw.exists():
            r = pd.read_parquet(raw).sort_values(["player", "t"])
            dts = float(r.groupby("player")["t"].diff().median())
        t = read_tables(d)
        res = run_pipeline(t, default_params())
        lab = res.labels
        cpt = lab[lab.cluster >= 0].groupby("t")["cluster"].nunique()
        rows.append(dict(match=d.name, points=len(t["positions"]), raw_dt_median=dts, t_max=t["meta"]["t_max"],
                         clusters_per_t=round(float(cpt.mean()), 2) if len(cpt) else 0, crowds=len(res.crowds),
                         gatherings=len(res.gatherings)))
        for kind, df in (("crowds", res.crowd_df), ("gatherings", res.gathering_df)):
            if len(df):
                ph.append(df.groupby("phase").size().rename(kind).to_frame().assign(match=d.name).reset_index())
    print(pd.DataFrame(rows).to_string(index=False))
    if ph:
        p = pd.concat(ph).groupby(["phase"])[["crowds", "gatherings"]].sum() / len(dirs)
        print("\nmean per match by phase:\n", p.round(2).to_string())


if __name__ == "__main__":
    main()
