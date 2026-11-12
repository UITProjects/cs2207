"""Multi-match aggregation at given parameters → tables used by Insights / Coach View.

Used by scripts/build_sample.py (precomputed for the default parameters into `_aggregates/`) and by
the app when the parameters differ from the defaults.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.analytics.gazetteer import nearest_place
from src.analytics.outcomes import exposure_rows, kill_inout, team_participation
from src.analytics.zone import annotate_zone
from src.mining.pipeline import run_pipeline
from src.parse.telemetry import read_tables


def mine_one(tables: dict, params: dict):
    res = run_pipeline(tables, params)
    g = res.gathering_df
    if len(g):
        g["place"] = [nearest_place(x, y) for x, y in zip(g["cx"], g["cy"], strict=True)]
    g = annotate_zone(g, tables["zones"])
    res.gathering_df = g
    return res, g


def aggregate(folder: Path, params: dict, progress=None) -> dict[str, pd.DataFrame]:
    dirs = sorted(d for d in Path(folder).iterdir() if (d / "meta.json").exists())
    G, E, T, K, M = [], [], [], [], []
    for i, d in enumerate(dirs):
        tables = read_tables(d)
        res, g = mine_one(tables, params)
        mid = tables["meta"]["match_id"]
        if len(g):
            G.append(g.drop(columns=["clusters"]).assign(match_id=mid))
        E.append(exposure_rows(tables, res, g))
        T.append(team_participation(tables, g))
        K.append(kill_inout(tables, res, g))
        M.append(dict(match_id=mid, n_crowds=len(res.crowds), n_gatherings=len(g)))
        if progress:
            progress((i + 1) / len(dirs))
    cat = lambda xs: pd.concat([x for x in xs if len(x)], ignore_index=True) if any(len(x) for x in xs) else pd.DataFrame()  # noqa: E731
    return dict(gatherings=cat(G), exposure=cat(E), teams=cat(T), kills=pd.DataFrame(K), matches=pd.DataFrame(M))


def save(agg: dict, out: Path, params: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for k, df in agg.items():
        df.to_parquet(out / f"{k}.parquet", index=False)
    (out / "info.json").write_text(json.dumps(dict(params=params, n_matches=len(agg["matches"]))), encoding="utf8")
