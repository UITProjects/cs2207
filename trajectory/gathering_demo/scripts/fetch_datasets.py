"""Download the real datasets baked into the app: PGS 12 Grand Final + the newest tournaments with Erangel
matches (fallback: newest ranked public matches), up to N Erangel matches each → data/raw/<dataset>/.

    uv run python scripts/fetch_datasets.py                 # needs PUBG_API_KEY (.env) and network (WARP)
    uv run python scripts/fetch_datasets.py --extra 2 --per 5

Then: parse + clean each dataset, and `scripts/build_sample.py --dataset <name>` to bake it into data/sample/.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.api.client import PubgClient  # noqa: E402
from src.config import path  # noqa: E402
from src.datasource.pubg_api import PubgApiDataSource, TournamentDataSource  # noqa: E402
from src.ingest.crawl import crawl, filters_for, passes_filters, write_dataset_info  # noqa: E402

log = logging.getLogger("fetch")
PINNED = {"as-pgs12gf": "PGS 12 Grand Final"}  # always included (user choice)
MAX_CANDIDATES = 8  # newest tournaments inspected for Erangel matches (each costs 1 rate-limited call)


def label_for(tid: str, created: str) -> str:
    if tid in PINNED:
        return PINNED[tid]
    return f"{tid.upper()} · {created[:10]}"


def erangel_matches(ds: TournamentDataSource, need: int = 1) -> int:
    """How many of the tournament's matches pass the tournament filters (stops early at `need`)."""
    filt, n = filters_for("tournament"), 0
    for mid in ds.list_match_ids(200):
        if passes_filters(ds.get_match(mid), filt)[0]:
            n += 1
            if n >= need:
                break
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--extra", type=int, default=2, help="newest tournaments to add besides the pinned ones")
    ap.add_argument("--per", type=int, default=5, help="Erangel matches per dataset")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    client = PubgClient(shard="tournament")
    tours = client._request(f"{client.base}/tournaments", limited=True).json()["data"]
    tours.sort(key=lambda d: d["attributes"].get("createdAt", ""), reverse=True)
    created = {d["id"]: d["attributes"].get("createdAt", "") for d in tours}

    chosen = [t for t in PINNED if t in created]
    for d in tours[:MAX_CANDIDATES]:
        if len(chosen) >= len(PINNED) + a.extra:
            break
        tid = d["id"]
        if tid in chosen:
            continue
        n = erangel_matches(TournamentDataSource(tid, client=client))
        log.info("candidate %s (%s): %s", tid, created[tid][:10], "Erangel ✓" if n else "no Erangel match")
        if n:
            chosen.append(tid)

    summary = []
    for tid in chosen:
        ds = TournamentDataSource(tid, client=client)
        st = crawl(ds, a.per)
        write_dataset_info(path("raw") / tid, dict(label=label_for(tid, created[tid]), kind="tournament",
                                                   tournament=tid, show_names=True, created=created[tid]))
        summary.append((tid, st))

    missing = len(PINNED) + a.extra - len(chosen)
    if missing > 0:  # not enough recent tournaments with Erangel: newest ranked public matches (no bots)
        ds = PubgApiDataSource(client=PubgClient())
        ds.name = "ranked-latest"
        ds.days = 2
        st = crawl(ds, a.per, list_limit=3000, filters=filters_for("ranked"))
        write_dataset_info(path("raw") / ds.name, dict(label="Ranked (mới nhất)", kind="ranked", show_names=False))
        summary.append((ds.name, st))
    print(json.dumps({k: v for k, v in summary}, indent=1))


if __name__ == "__main__":
    main()
