"""Raw match.json + telemetry → tables (meters, seconds since LogMatchStart, anonymised ids).

Tables: positions, landings, zones, kills, results (+ meta dict). Works the same on mock and real
files: it only relies on the shapes in docs/schema.md.

    uv run python -m src.parse.telemetry --all [--source mock]
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import logging
from pathlib import Path

import pandas as pd

from src.config import datasource_name, load_config, path
from src.datasource.schema import unwrap_character

log = logging.getLogger("parse")
CM = 100.0


def parse_time(s: str) -> dt.datetime:
    s = s.rstrip("Z")
    if "." in s:
        head, frac = s.split(".")
        s = f"{head}.{frac[:6].ljust(6, '0')}"
    return dt.datetime.fromisoformat(s)


def load_raw(match_dir: Path) -> tuple[dict, list[dict]]:
    match = json.loads((match_dir / "match.json").read_text(encoding="utf8"))
    with gzip.open(match_dir / "telemetry.json.gz", "rt", encoding="utf8") as f:
        tel = json.load(f)
    return match, tel


def is_bot(c: dict) -> bool:
    """AI bots (`ai.` accountId / type user_ai) and NPCs (type monster) — public matches are full of them."""
    return str(c.get("accountId", "")).startswith("ai.") or c.get("type") in ("monster", "user_ai")


def build_ids(tel: list[dict], drop_bots: bool = True) -> tuple[dict[str, str], dict[int, str]]:
    """accountId → P001…, teamId → T01…, ordered by (teamId, accountId). Bots/NPCs are skipped by default."""
    seen: dict[str, int] = {}

    def add(c: dict) -> None:
        if c.get("accountId") and not (drop_bots and is_bot(c)):
            seen.setdefault(c["accountId"], int(c.get("teamId", 0)))

    for e in tel:
        for key in ("character", "victim", "killer"):
            c = e.get(key)
            if isinstance(c, dict):
                add(c)
        if e.get("_T") in ("LogMatchStart", "LogMatchEnd"):
            for item in e.get("characters", []):
                add(unwrap_character(item))
    players = sorted(seen, key=lambda a: (seen[a], a))
    pid = {a: f"P{i + 1:03d}" for i, a in enumerate(players)}
    teams = sorted(set(seen.values()))
    tid = {t: f"T{i + 1:02d}" for i, t in enumerate(teams)}
    return pid, tid


def team_tag(names: list[str]) -> str | None:
    """Most common prefix before '_' among the members' names (tournament style 'MiTH_Baren' → 'MiTH')."""
    tags = [n.split("_", 1)[0] for n in names if "_" in n and n.split("_", 1)[0]]
    return max(set(tags), key=lambda t: (tags.count(t), t)) if tags else None


def players_table(tel: list[dict], pid: dict[str, str], tid: dict[int, str], keep_names: bool) -> pd.DataFrame:
    """player/team ids with display names. Real names only when keep_names (tournaments); else name = id."""
    raw_name: dict[str, str] = {}
    team_of: dict[str, str] = {}

    def see(c) -> None:
        if isinstance(c, dict) and c.get("accountId") in pid:
            raw_name.setdefault(c["accountId"], str(c.get("name", "")))
            team_of.setdefault(c["accountId"], tid[int(c["teamId"])])

    for e in tel:
        see(e.get("character"))
        if e.get("_T") in ("LogMatchStart", "LogMatchEnd"):  # players who never moved still have a team/name
            for item in e.get("characters", []):
                see(unwrap_character(item))
    for a in pid:
        team_of.setdefault(a, "")
    rows = []
    by_team: dict[str, list[str]] = {}
    for a in pid:
        by_team.setdefault(team_of[a], []).append(raw_name.get(a, ""))
    tags = {t: team_tag(ns) for t, ns in by_team.items()}
    for a, p in sorted(pid.items(), key=lambda kv: kv[1]):
        t = team_of[a]
        if keep_names and raw_name.get(a):
            full = raw_name[a]
            tag = tags.get(t)
            name = full.split("_", 1)[1] if tag and full.startswith(tag + "_") else full
            team_name = tag or t
        else:
            name, team_name = p, t
        rows.append((p, t, name, team_name))
    return pd.DataFrame(rows, columns=["player", "team", "name", "team_name"])


def parse_match(match: dict, tel: list[dict], keep_names: bool = False, drop_bots: bool = True) -> dict:
    """Raw match + telemetry → tables. keep_names: keep real player/team names (tournaments only)."""
    attrs = match["data"]["attributes"]
    mid = match["data"]["id"]
    start = next(e for e in tel if e["_T"] == "LogMatchStart")
    t0 = parse_time(start["_D"])
    pid, tid = build_ids(tel, drop_bots)

    def ts(e: dict) -> float:
        return (parse_time(e["_D"]) - t0).total_seconds()

    pos, land, zones, kills, results = [], [], [], [], []
    for e in tel:
        T = e["_T"]
        if T in ("LogPlayerPosition", "LogParachuteLanding", "LogGameStatePeriodic") and ts(e) < 0:
            continue  # pre-match lobby (tournament telemetry starts ~2 min before LogMatchStart)
        if T == "LogPlayerPosition":
            c = e["character"]
            if c.get("accountId") not in pid:  # bot / NPC
                continue
            loc = c["location"]
            veh = e.get("vehicle") or {}
            pos.append((pid[c["accountId"]], tid[int(c["teamId"])], ts(e), loc["x"] / CM, loc["y"] / CM,
                        loc.get("z", 0) / CM, float(c.get("health", 0)), bool(veh.get("vehicleId")),
                        int(e.get("numAlivePlayers", 0))))
        elif T == "LogParachuteLanding":  # can repeat per player; the first one is kept below (groupby min)
            c = e["character"]
            if c.get("accountId") in pid:
                land.append((pid[c["accountId"]], ts(e)))
        elif T == "LogGameStatePeriodic":
            g = e["gameState"]
            sp, wp = g["safetyZonePosition"], g["poisonGasWarningPosition"]
            zones.append((ts(e), sp["x"] / CM, sp["y"] / CM, g["safetyZoneRadius"] / CM, wp["x"] / CM,
                          wp["y"] / CM, g["poisonGasWarningRadius"] / CM, int(g.get("numAlivePlayers", 0)),
                          int(g.get("numAliveTeams", 0))))
        elif T == "LogPlayerKillV2":
            v, k = e["victim"], e.get("killer") or e.get("finisher")
            if not isinstance(v, dict) or v.get("accountId") not in pid:  # bot victim
                continue
            k_ok = isinstance(k, dict) and k.get("accountId") in pid
            kills.append((ts(e), pid[k["accountId"]] if k_ok else None, pid[v["accountId"]],
                          tid[int(k["teamId"])] if k_ok else None, tid[int(v["teamId"])],
                          v["location"]["x"] / CM, v["location"]["y"] / CM))
        elif T == "LogMatchEnd":
            rk: dict[str, int] = {}
            for item in e.get("characters", []):
                c = unwrap_character(item)
                if c.get("accountId") in pid:
                    rk[tid[int(c["teamId"])]] = int(c.get("ranking", 0))
            results = sorted(rk.items())

    tables = dict(
        positions=pd.DataFrame(pos, columns=["player", "team", "t", "x", "y", "z", "health", "in_vehicle", "num_alive"]),
        landings=pd.DataFrame(land, columns=["player", "t_land"]).groupby("player", as_index=False).min(),
        zones=pd.DataFrame(zones, columns=["t", "safe_x", "safe_y", "safe_r", "warn_x", "warn_y", "warn_r",
                                           "alive_players", "alive_teams"]),
        kills=pd.DataFrame(kills, columns=["t", "killer", "victim", "killer_team", "victim_team", "x", "y"]),
        results=pd.DataFrame(results, columns=["team", "ranking"]),
        players=players_table(tel, pid, tid, keep_names),
    )
    for name, df in tables.items():
        if "t" in df:
            tables[name] = df.sort_values("t", kind="stable").reset_index(drop=True)
        df.insert(0, "match_id", mid) if "match_id" not in df else None
    tables["meta"] = dict(match_id=mid, mapName=attrs.get("mapName"), gameMode=attrs.get("gameMode"),
                          matchType=attrs.get("matchType"), createdAt=attrs.get("createdAt"),
                          duration=attrs.get("duration"), n_players=len(pid), n_teams=len(tid),
                          start=start["_D"], names=bool(keep_names))
    return tables


def write_tables(tables: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        if name == "meta":
            (out / "meta.json").write_text(json.dumps(df, indent=1), encoding="utf8")
        else:
            df.to_parquet(out / f"{name}.parquet", index=False)


def read_tables(d: Path) -> dict:
    t = {p.stem: pd.read_parquet(p) for p in d.glob("*.parquet")}
    t["meta"] = json.loads((d / "meta.json").read_text(encoding="utf8"))
    return t


def dataset_info(raw_dir: Path) -> dict:
    """`dataset.json` next to the match folders (label, kind, show_names, …); {} for mock / legacy folders."""
    f = raw_dir / "dataset.json"
    return json.loads(f.read_text(encoding="utf8")) if f.exists() else {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dataset", "--source", dest="dataset", default=None, help="folder under data/raw")
    ap.add_argument("--match", default=None)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    src = a.dataset or datasource_name()
    raw = path("raw") / src
    info = dataset_info(raw)
    drop_bots = bool(load_config().get("preprocess", {}).get("drop_bots", True))
    dirs = [raw / a.match] if a.match else sorted(p for p in raw.iterdir() if (p / "telemetry.json.gz").exists())
    n = 0
    for d in dirs:
        out = path("interim") / src / d.name
        if (out / "meta.json").exists() and not a.force:
            continue
        write_tables(parse_match(*load_raw(d), keep_names=bool(info.get("show_names")), drop_bots=drop_bots), out)
        n += 1
    log.info("parsed %d matches (%d already done) -> %s", n, len(dirs) - n, path("interim") / src)


if __name__ == "__main__":
    main()
