"""Pick N processed matches with good gathering coverage → data/sample/{source}/ (committed, offline demo).

    uv run python scripts/build_sample.py --n 30 [--source mock]
    uv run python scripts/build_sample.py --match mock-2207-0001     # exactly these match(es)
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.analytics.gazetteer import nearest_place  # noqa: E402
from src.config import datasource_name, default_params, path  # noqa: E402
from src.mining.pipeline import run_pipeline  # noqa: E402
from src.parse.telemetry import read_tables  # noqa: E402

KEEP = ["positions.parquet", "zones.parquet", "kills.parquet", "results.parquet", "meta.json"]


def score(d: Path, params: dict) -> float:
    g = run_pipeline(read_tables(d), params).gathering_df
    if g.empty:
        return 0.0
    bridges = sum("Bridge" in nearest_place(x, y) for x, y in zip(g["cx"], g["cy"], strict=True))
    return len(g) + 2 * g["phase"].nunique() + 3 * bridges


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--source", default=None)
    ap.add_argument("--match", action="append", default=None, help="keep exactly these match ids (repeatable)")
    a = ap.parse_args()
    src = a.source or datasource_name()
    src_dir = path("processed") / src
    out = path("sample") / ("real" if src == "pubg" else src)
    params = default_params()
    dirs = sorted(d for d in src_dir.iterdir() if (d / "meta.json").exists())
    if a.match:
        ranked = [d for d in dirs if d.name in set(a.match)]
        missing = set(a.match) - {d.name for d in ranked}
        if missing:
            sys.exit(f"not found in {src_dir}: {sorted(missing)}")
    else:
        ranked = sorted(dirs, key=lambda d: -score(d, params))[: a.n]
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for d in sorted(ranked):
        (out / d.name).mkdir()
        for f in KEEP:
            shutil.copy2(d / f, out / d.name / f)
        gt = path("raw") / src / d.name / "ground_truth.json"
        if gt.exists():
            shutil.copy2(gt, out / d.name / "ground_truth.json")
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(json.dumps(dict(source=src, out=str(out), matches=len(ranked),
                          size_mb=round(size / 1e6, 2))))


if __name__ == "__main__":
    main()
