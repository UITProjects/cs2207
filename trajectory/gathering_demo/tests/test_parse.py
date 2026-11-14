"""Parser/cleaning contract tests. Run on mock output now; real fixtures (tests/fixtures/real) at M8."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.datasource.mock import MockDataSource
from src.parse.telemetry import parse_match
from src.preprocess.clean import clean_match, label_phases, resample

FIX = Path(__file__).parent / "fixtures"


def _mock_pair():
    ds = MockDataSource(seed=7)
    mid = next(m for m in ds.list_match_ids(20) if ds.get_match(m)["data"]["attributes"]["mapName"] == "Baltic_Main"
               and ds.get_match(m)["data"]["attributes"]["gameMode"].startswith("squad"))
    m = ds.get_match(mid)
    return m, ds.get_telemetry(m)


def _real_pairs():
    import gzip
    import json

    out = []
    for d in sorted((FIX / "real").glob("*")) if (FIX / "real").exists() else []:
        out.append((json.loads((d / "match.json").read_text()), json.load(gzip.open(d / "telemetry.json.gz", "rt"))))
    return out


SOURCES = [pytest.param(_mock_pair, id="mock")] + [pytest.param(lambda p=p: p, id=f"real{i}")
                                                     for i, p in enumerate(_real_pairs())]


@pytest.mark.parametrize("get", SOURCES)
def test_contract(get):
    match, tel = get()
    t = parse_match(match, tel)
    pos = t["positions"]
    assert {"player", "team", "t", "x", "y", "z", "in_vehicle"} <= set(pos.columns)
    assert pos["player"].str.fullmatch(r"P\d{3}").all() and pos["team"].str.fullmatch(r"T\d{2}").all()
    assert pos["t"].min() >= 0
    landed = pos.merge(t["landings"], on="player")
    landed = landed[landed["t"] > landed["t_land"] + 5]
    assert landed["x"].between(0, 8160).all() and landed["y"].between(0, 8160).all()  # meters, on the map
    assert t["zones"]["warn_r"].max() < 10000 and len(t["results"]) > 1
    assert t["kills"]["victim"].notna().all()
    c = clean_match(t)
    p = c["positions"]
    assert (p["t"] % 10 == 0).all() and p.groupby(["player", "t"]).size().max() == 1
    assert p["phase"].min() >= 0 and c["meta"]["n_phases"] >= 3


def test_resample_interpolates_short_gaps_only():
    g = pd.DataFrame({"t": [0.0, 10.0, 20.0, 80.0, 90.0], "x": [0, 10, 20, 80, 90.0], "y": 0.0, "in_vehicle": False})
    r = resample(g, 10, 30)
    assert list(r["t"]) == [0, 10, 20, 80, 90]  # 30..70 is a 60 s gap: left empty
    g2 = pd.DataFrame({"t": [1.0, 12.0, 21.0], "x": [1.0, 12.0, 21.0], "y": 0.0, "in_vehicle": False})
    r2 = resample(g2, 10, 30)
    assert list(r2["t"]) == [10, 20] and np.allclose(r2["x"], [10, 20])


def test_phase_labels():
    z = pd.DataFrame({"t": [0, 10, 20, 30, 40], "warn_r": [5800, 5800, 2900, 2900, 1800]})
    assert list(label_phases(z)["phase"]) == [0, 0, 1, 1, 2]
