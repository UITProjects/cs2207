"""Coach takeaways and VOD flags on the committed sample match + a synthetic losses case."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from src.analytics.coach import VOD_COLUMNS, losses, match_insights, vod_flags
from src.analytics.gazetteer import nearest_place
from src.analytics.movement import team_summary
from src.config import default_params, path
from src.mining.pipeline import run_pipeline
from src.parse.telemetry import read_tables


@pytest.fixture(scope="module")
def sample():
    d = next(p for p in sorted((path("sample") / "mock").iterdir()) if (p / "meta.json").exists())
    t = read_tables(Path(d))
    r = run_pipeline(t, default_params())
    r.gathering_df["place"] = [nearest_place(x, y) for x, y in zip(r.gathering_df["cx"], r.gathering_df["cy"],
                                                                     strict=True)]
    return t, r, team_summary(t, r.gathering_df)


def test_insights_cover_four_takeaways(sample):
    t, r, s = sample
    ins = match_insights(t, r, s, r.gathering_df)
    keys = [i["key"] for i in ins]
    assert keys == ["hot_drop", "winner_route", "chokepoint", "danger_rate"]
    ids = set(r.gathering_df["id"].astype(int))
    for i in ins:
        assert i["advice"] and i["big"] and set(i["evidence"]) <= ids
    lost, present = map(int, ins[0]["big"].split("/"))
    assert 0 < lost <= present
    assert ins[1]["big"] == s.sort_values("rank").iloc[0]["team"]
    assert float(ins[3]["big"].lstrip("×")) > 0


def test_vod_flags_sorted_and_empty(sample):
    t, r, s = sample
    involved = r.gathering_df["teams"].explode()
    team = involved.value_counts().index[0]
    v = vod_flags(t, r, r.gathering_df, team)
    assert len(v) == (involved == team).sum()
    assert list(v.columns[: len(VOD_COLUMNS)]) == VOD_COLUMNS and v["t_start"].is_monotonic_increasing
    assert all(team not in met for met in v["teams_met"])
    outsider = next(tm for tm in s["team"] if tm not in set(involved))
    assert vod_flags(t, r, r.gathering_df, outsider).empty


def test_losses_synthetic():
    pos = pd.DataFrame(dict(player=["A1", "A2", "B1", "B2", "C1"], team=["TA", "TA", "TB", "TB", "TC"],
                            t=[0] * 5, x=[0.0] * 5, y=[0.0] * 5))
    kills = pd.DataFrame(dict(t=[50.0, 60.0, 150.0, 400.0, 5.0], victim=["A1", "A2", "B1", "B2", "C1"]))
    row = SimpleNamespace(teams=["TA", "TB", "TC"], t_start=20.0, t_end=100.0)
    lo = losses(dict(positions=pos, kills=kills), row)
    assert lo["present"] == 4  # C1 died before the gathering started
    assert lo["lost"] == 3 and lo["wiped"] == ["TA"]  # B1 at 150 ≤ 100 + 120; B2 at 400 survives the window
