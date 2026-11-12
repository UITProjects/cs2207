"""Print the actual schema of one raw telemetry file (mock or real): event counts, keys per event
type (with nested keys of the events we use) and the LogPlayerPosition Δt distribution.

    uv run python scripts/inspect_telemetry.py data/raw/mock/mock-2207-0000/telemetry.json.gz
"""
from __future__ import annotations

import gzip
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.parse.telemetry import parse_time  # noqa: E402

USED = {"LogMatchStart", "LogPlayerPosition", "LogParachuteLanding", "LogGameStatePeriodic", "LogPlayerKillV2",
        "LogMatchEnd"}


def keys(o, prefix="", depth=2) -> set[str]:
    out = set()
    if isinstance(o, dict):
        for k, v in o.items():
            out.add(f"{prefix}{k}:{type(v).__name__}")
            if depth > 0 and isinstance(v, dict):
                out |= keys(v, f"{prefix}{k}.", depth - 1)
            if depth > 0 and isinstance(v, list) and v and isinstance(v[0], dict):
                out |= keys(v[0], f"{prefix}{k}[].", depth - 1)
    return out


def main(p: str) -> None:
    f = Path(p)
    ev = json.load(gzip.open(f, "rt", encoding="utf8") if f.suffix == ".gz" else open(f, encoding="utf8"))
    cnt = Counter(e["_T"] for e in ev)
    print(f"{len(ev)} events, {len(cnt)} types")
    for k, v in cnt.most_common():
        print(f"  {v:7d} {k}{'  *' if k in USED else ''}")
    schema = defaultdict(set)
    for e in ev:
        if e["_T"] in USED and len(schema[e["_T"]]) < 400:
            schema[e["_T"]] |= keys(e)
    for t in sorted(schema):
        print(f"\n== {t}")
        for k in sorted(schema[t]):
            print("   ", k)
    last, dts = {}, []
    for e in ev:
        if e["_T"] == "LogPlayerPosition":
            a, tt = e["character"]["accountId"], parse_time(e["_D"])
            if a in last:
                dts.append((tt - last[a]).total_seconds())
            last[a] = tt
    if dts:
        d = np.array(dts)
        print(f"\nLogPlayerPosition Δt per player: n={len(d)} median={np.median(d):.2f}s "
              f"p10={np.percentile(d, 10):.2f} p90={np.percentile(d, 90):.2f} max={d.max():.1f}")
    maps = {e.get("mapName") for e in ev if e["_T"] == "LogMatchStart"}
    print("mapName:", maps)


if __name__ == "__main__":
    main(sys.argv[1])
