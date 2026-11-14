"""Crawl matches from any DataSource → data/raw/{dataset}/{match_id}/ (idempotent).

    DATASOURCE=mock uv run python -m src.ingest.crawl --max-matches 50
    DATASOURCE=pubg uv run python -m src.ingest.crawl --days 1 --max-matches 200
    uv run python -m src.ingest.crawl --tournament as-pgs12gf --dataset pgs12-gf --max-matches 5
"""
from __future__ import annotations

import argparse
import gzip
import json
import logging
import time
from pathlib import Path

from src.config import load_config, path
from src.datasource.base import DataSource, get_datasource

log = logging.getLogger("crawl")


def passes_filters(match: dict, filters: dict) -> tuple[bool, str]:
    a = match["data"]["attributes"]
    for key in ("mapName", "gameMode", "matchType"):
        allowed = filters.get(key)
        if allowed and a.get(key) not in allowed:
            return False, f"{key}={a.get(key)}"
    if a.get("duration", 0) < filters.get("min_duration_s", 0):  # aborted / remade games
        return False, f"duration={a.get('duration')}"
    return True, ""


def filters_for(kind: str) -> dict:
    """config.yaml `filters` (public samples) or `filters_<kind>` (e.g. filters_tournament)."""
    cfg = load_config()
    return cfg.get(f"filters_{kind}") or cfg["filters"]


def crawl(ds: DataSource, max_matches: int, out_root: Path | None = None, list_limit: int | None = None,
          filters: dict | None = None) -> dict:
    out_root = (out_root or path("raw")) / ds.name
    filters = filters if filters is not None else filters_for(getattr(ds, "kind", "public"))
    stats = dict(listed=0, fetched=0, filtered=0, skipped=0, failed=0)
    # /samples is one request returning every id; most real samples are other maps/modes and /matches is not
    # rate limited, so scan many ids for pubg. Mock ids almost all pass the filters.
    ids = ds.list_match_ids(list_limit or max_matches * (3 if ds.name == "mock" else 400))
    stats["listed"] = len(ids)
    for mid in ids:
        if stats["fetched"] + stats["skipped"] >= max_matches:
            break
        d = out_root / mid
        if (d / "telemetry.json.gz").exists() and (d / "match.json").exists():
            stats["skipped"] += 1
            continue
        try:
            match = ds.get_match(mid)
            ok, why = passes_filters(match, filters)
            if not ok:
                stats["filtered"] += 1
                log.debug("filtered %s (%s)", mid, why)
                continue
            tel = ds.get_telemetry(match)
            d.mkdir(parents=True, exist_ok=True)
            (d / "match.json").write_text(json.dumps(match), encoding="utf8")
            if hasattr(ds, "get_ground_truth"):
                (d / "ground_truth.json").write_text(json.dumps(ds.get_ground_truth(mid), indent=1), encoding="utf8")
            tmp = d / "telemetry.json.gz.tmp"
            with gzip.open(tmp, "wt", encoding="utf8") as f:
                json.dump(tel, f)
            tmp.rename(d / "telemetry.json.gz")  # written last: its presence marks a complete match
            stats["fetched"] += 1
            log.info("fetched %s (%d events)", mid, len(tel))
        except Exception as e:  # noqa: BLE001 — keep crawling, report at the end
            from src.api.errors import NetworkBlockedError

            if isinstance(e, NetworkBlockedError):
                raise
            stats["failed"] += 1
            log.warning("failed %s: %s", mid, e)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-matches", type=int, default=50)
    ap.add_argument("--days", type=int, default=1, help="(pubg) days of /samples to read; mock ignores it")
    ap.add_argument("--source", default=None, help="mock | pubg (default: env DATASOURCE / config.yaml)")
    ap.add_argument("--list-limit", type=int, default=None, help="max sample ids to scan (default: 3×/400× max)")
    ap.add_argument("--tournament", default=None, help="tournament id (e.g. as-pgs12gf): crawl its matches")
    ap.add_argument("--dataset", default=None, help="folder name under data/raw (default: source / tournament id)")
    ap.add_argument("--label", default=None, help="dataset label shown in the app")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    if args.tournament:
        from src.datasource.pubg_api import TournamentDataSource

        ds = TournamentDataSource(args.tournament, name=args.dataset or args.tournament)
    else:
        ds = get_datasource(args.source)
        if args.dataset:
            ds.name = args.dataset
        if hasattr(ds, "days"):
            ds.days = args.days
    t0 = time.time()
    st = crawl(ds, args.max_matches, list_limit=args.list_limit)
    if args.tournament:
        write_dataset_info(path("raw") / ds.name, dict(
            label=args.label or args.tournament, kind="tournament", tournament=args.tournament, show_names=True,
            created=max((ds.created.get(m, "") for m in ds.created), default="")))
    log.info("dataset=%s %s in %.1fs", ds.name, st, time.time() - t0)


def write_dataset_info(folder: Path, info: dict) -> None:
    """dataset.json next to the match folders; keeps keys already there (e.g. a chosen showcase)."""
    folder.mkdir(parents=True, exist_ok=True)
    f = folder / "dataset.json"
    old = json.loads(f.read_text(encoding="utf8")) if f.exists() else {}
    f.write_text(json.dumps({**old, **{k: v for k, v in info.items() if v is not None}}, indent=1), encoding="utf8")


if __name__ == "__main__":
    main()
