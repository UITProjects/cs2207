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

from src.config import datasource_name, path
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


def build_ids(tel: list[dict]) -> tuple[dict[str, str], dict[int, str]]:
    """accountId → P001…, teamId → T01…, ordered by (teamId, accountId). No names are kept."""
    seen: dict[str, int] = {}
    for e in tel:
        for key in ("character", "victim", "killer"):
            c = e.get(key)
            if isinstance(c, dict) and c.get("accountId"):
                seen.setdefault(c["accountId"], int(c.get("teamId", 0)))
        if e.get("_T") in ("LogMatchStart", "LogMatchEnd"):
            for item in e.get("characters", []):
                c = unwrap_character(item)
                if c.get("accountId"):
                    seen.setdefault(c["accountId"], int(c.get("teamId", 0)))
    players = sorted(seen, key=lambda a: (seen[a], a))
    pid = {a: f"P{i + 1:03d}" for i, a in enumerate(players)}
    teams = sorted(set(seen.values()))
    tid = {t: f"T{i + 1:02d}" for i, t in enumerate(teams)}
    return pid, tid


def parse_match(match: dict, tel: list[dict]) -> dict:
    attrs = match["data"]["attributes"]
    mid = match["data"]["id"]
    start = next(e for e in tel if e["_T"] == "LogMatchStart")
    t0 = parse_time(start["_D"])
    pid, tid = build_ids(tel)

    def ts(e: dict) -> float:
        return (parse_time(e["_D"]) - t0).total_seconds()

    pos, land, zones, kills, results = [], [], [], [], []
    for e in tel:
        T = e["_T"]
        if T == "LogPlayerPosition":
            c = e["character"]
            loc = c["location"]
            veh = e.get("vehicle") or {}
            pos.append((pid[c["accountId"]], tid[int(c["teamId"])], ts(e), loc["x"] / CM, loc["y"] / CM,
                        loc.get("z", 0) / CM, float(c.get("health", 0)), bool(veh.get("vehicleId")),
                        int(e.get("numAlivePlayers", 0))))
        elif T == "LogParachuteLanding":
            c = e["character"]
            land.append((pid[c["accountId"]], ts(e)))
        elif T == "LogGameStatePeriodic":
            g = e["gameState"]
            sp, wp = g["safetyZonePosition"], g["poisonGasWarningPosition"]
            zones.append((ts(e), sp["x"] / CM, sp["y"] / CM, g["safetyZoneRadius"] / CM, wp["x"] / CM,
                          wp["y"] / CM, g["poisonGasWarningRadius"] / CM, int(g.get("numAlivePlayers", 0)),
                          int(g.get("numAliveTeams", 0))))
        elif T == "LogPlayerKillV2":
            v, k = e["victim"], e.get("killer") or e.get("finisher")
            k_ok = isinstance(k, dict) and k.get("accountId") in pid
            kills.append((ts(e), pid[k["accountId"]] if k_ok else None, pid[v["accountId"]],
                          tid[int(k["teamId"])] if k_ok else None, tid[int(v["teamId"])],
                          v["location"]["x"] / CM, v["location"]["y"] / CM))
        elif T == "LogMatchEnd":
            rk: dict[str, int] = {}
            for item in e.get("characters", []):
                c = unwrap_character(item)
                rk[tid[int(c["teamId"])]] = int(c.get("ranking", 0))
            results = sorted(rk.items())

    tables = dict(
        positions=pd.DataFrame(pos, columns=["player", "team", "t", "x", "y", "z", "health", "in_vehicle", "num_alive"]),
        landings=pd.DataFrame(land, columns=["player", "t_land"]).groupby("player", as_index=False).min(),
        zones=pd.DataFrame(zones, columns=["t", "safe_x", "safe_y", "safe_r", "warn_x", "warn_y", "warn_r",
                                           "alive_players", "alive_teams"]),
        kills=pd.DataFrame(kills, columns=["t", "killer", "victim", "killer_team", "victim_team", "x", "y"]),
        results=pd.DataFrame(results, columns=["team", "ranking"]),
    )
    for name, df in tables.items():
        if "t" in df:
            tables[name] = df.sort_values("t", kind="stable").reset_index(drop=True)
        df.insert(0, "match_id", mid) if "match_id" not in df else None
    tables["meta"] = dict(match_id=mid, mapName=attrs.get("mapName"), gameMode=attrs.get("gameMode"),
                          matchType=attrs.get("matchType"), createdAt=attrs.get("createdAt"),
                          duration=attrs.get("duration"), n_players=len(pid), n_teams=len(tid),
                          start=start["_D"])
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--source", default=None)
    ap.add_argument("--match", default=None)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    src = a.source or datasource_name()
    raw = path("raw") / src
    dirs = [raw / a.match] if a.match else sorted(p for p in raw.iterdir() if (p / "telemetry.json.gz").exists())
    n = 0
    for d in dirs:
        out = path("interim") / src / d.name
        if (out / "meta.json").exists() and not a.force:
            continue
        write_tables(parse_match(*load_raw(d)), out)
        n += 1
    log.info("parsed %d matches (%d already done) -> %s", n, len(dirs) - n, path("interim") / src)


if __name__ == "__main__":
    main()
