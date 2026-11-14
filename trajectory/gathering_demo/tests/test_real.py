"""Real-data features: player/team names (tournaments only), bot filtering, tournament source + filters,
dataset discovery. Uses the trimmed real fixture (tests/fixtures/real, names masked as TAG_pN)."""
from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path

import pytest
import responses

from src.ingest.crawl import filters_for, passes_filters
from src.parse.telemetry import is_bot, parse_match, team_tag

FIX = Path(__file__).parent / "fixtures" / "real"


@pytest.fixture(scope="module")
def real():
    d = next(p for p in sorted(FIX.iterdir()) if p.is_dir())
    return json.loads((d / "match.json").read_text()), json.load(gzip.open(d / "telemetry.json.gz", "rt"))


def test_names_only_when_kept(real):
    m, tel = real
    hidden = parse_match(m, tel)["players"]
    assert (hidden["name"] == hidden["player"]).all() and (hidden["team_name"] == hidden["team"]).all()
    shown = parse_match(m, tel, keep_names=True)["players"]
    assert shown["name"].str.fullmatch(r"p\d+").all()  # 'MiTH_p3' → tag stripped → 'p3'
    assert (shown["team_name"] != shown["team"]).all()  # every team got its tag
    assert shown.groupby("team")["team_name"].nunique().eq(1).all()


def test_team_tag():
    assert team_tag(["MiTH_Baren", "MiTH_Jacob", "MiTH_KISS", "Sub_X"]) == "MiTH"
    assert team_tag(["noprefix", "alsonone"]) is None


def test_bots_and_npcs_dropped(real):
    m, tel = real
    tel = copy.deepcopy(tel)
    pos_ev = next(e for e in tel if e["_T"] == "LogPlayerPosition")
    for i, (acc, typ) in enumerate([("ai.123", "user_ai"), ("account.npc", "monster")]):
        bot = copy.deepcopy(pos_ev)
        bot["character"].update(accountId=acc, type=typ, teamId=900 + i)
        tel.append(bot)
    assert is_bot({"accountId": "ai.1"}) and is_bot({"accountId": "account.x", "type": "monster"})
    t = parse_match(m, tel)
    assert t["meta"]["n_teams"] == parse_match(m, real[1])["meta"]["n_teams"]  # bot teams not added
    kept = parse_match(m, tel, drop_bots=False)
    assert kept["meta"]["n_teams"] == t["meta"]["n_teams"] + 2


def test_no_lobby_positions(real):
    m, tel = real
    assert parse_match(m, tel)["positions"]["t"].min() >= 0


def test_tournament_filters():
    f = filters_for("tournament")
    ok = {"data": {"attributes": {"mapName": "Baltic_Main", "gameMode": "esports-squad", "matchType": "",
                                  "duration": 1700}}}
    assert passes_filters(ok, f)[0]
    short = copy.deepcopy(ok)
    short["data"]["attributes"]["duration"] = 16
    assert not passes_filters(short, f)[0]  # aborted game
    other = copy.deepcopy(ok)
    other["data"]["attributes"]["mapName"] = "Tiger_Main"
    assert not passes_filters(other, f)[0]


@responses.activate
def test_tournament_datasource(monkeypatch):
    monkeypatch.setenv("PUBG_API_KEY", "test-key-not-real")
    from src.api.client import PubgClient
    from src.datasource.pubg_api import TournamentDataSource

    base = "https://api.pubg.com"
    responses.get(f"{base}/tournaments/as-x", json={
        "data": {"id": "as-x", "relationships": {"matches": {"data": [{"type": "match", "id": "m1"},
                                                                       {"type": "match", "id": "m2"}]}}},
        "included": [{"type": "match", "id": "m1", "attributes": {"createdAt": "2026-10-30T10:00:00Z"}},
                     {"type": "match", "id": "m2", "attributes": {"createdAt": "2026-11-01T10:00:00Z"}}]})
    responses.get(f"{base}/shards/tournament/matches/m2", json={"data": {"id": "m2", "attributes": {}}})
    ds = TournamentDataSource("as-x", client=PubgClient(shard="tournament", sleep=lambda s: None))
    assert ds.list_match_ids(10) == ["m2", "m1"]  # newest first
    assert ds.get_match("m2")["data"]["id"] == "m2"
    assert responses.calls[0].request.headers["Authorization"].startswith("Bearer ")


def test_datasets_discovery():
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
    import common

    ds = common.datasets()
    assert "mock" in ds and list(ds)[-1] == "mock"  # mock last
    real = [d for d in ds.values() if d["kind"] == "tournament"]
    assert len(real) >= 3, "≥ 3 real datasets are baked into data/sample"
    assert [d["created"] for d in real] == sorted((d["created"] for d in real), reverse=True)  # newest first
    for d in real:
        assert d["show_names"] and d["showcase"] and (Path(d["folder"]) / d["showcase"] / "meta.json").exists()
