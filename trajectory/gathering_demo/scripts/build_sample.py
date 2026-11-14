"""Bake a processed dataset into data/sample/<dataset>/ (committed; the Docker image ships it):
the N matches with the best gathering coverage (or --match …), + dataset.json with the showcase match.

    uv run python scripts/build_sample.py --dataset as-pgs12gf
    uv run python scripts/build_sample.py --n 30 [--dataset mock]
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

KEEP = ["positions.parquet", "zones.parquet", "kills.parquet", "results.parquet", "players.parquet", "meta.json"]


def score(d: Path, params: dict) -> float:
    g = run_pipeline(read_tables(d), params).gathering_df
    if g.empty:
        return 0.0
    bridges = sum("Bridge" in nearest_place(x, y) for x, y in zip(g["cx"], g["cy"], strict=True))
    return len(g) + 2 * g["phase"].nunique() + 3 * bridges


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--dataset", "--source", dest="dataset", default=None, help="folder under data/processed")
    ap.add_argument("--match", action="append", default=None, help="keep exactly these match ids (repeatable)")
    a = ap.parse_args()
    src = a.dataset or datasource_name()
    src_dir = path("processed") / src
    out = path("sample") / src
    params = default_params()
    dirs = sorted(d for d in src_dir.iterdir() if (d / "meta.json").exists())
    if a.match:
        ranked = [d for d in dirs if d.name in set(a.match)]
        missing = set(a.match) - {d.name for d in ranked}
        if missing:
            sys.exit(f"not found in {src_dir}: {sorted(missing)}")
    scores = {d.name: score(d, params) for d in dirs}
    if not a.match:
        ranked = sorted(dirs, key=lambda d: -scores[d.name])[: a.n]
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for d in sorted(ranked):
        (out / d.name).mkdir()
        for f in KEEP:
            if (d / f).exists():
                shutil.copy2(d / f, out / d.name / f)
        gt = path("raw") / src / d.name / "ground_truth.json"
        if gt.exists():
            shutil.copy2(gt, out / d.name / "ground_truth.json")
    info_f = path("raw") / src / "dataset.json"
    info = json.loads(info_f.read_text(encoding="utf8")) if info_f.exists() else {}
    info.setdefault("label", src)
    info.setdefault("kind", "mock" if src == "mock" else "public")
    info["showcase"] = max(ranked, key=lambda d: scores[d.name]).name  # best gathering coverage opens first
    (out / "dataset.json").write_text(json.dumps(info, indent=1, ensure_ascii=False), encoding="utf8")
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(json.dumps(dict(dataset=src, out=str(out), matches=len(ranked), showcase=info["showcase"],
                          size_mb=round(size / 1e6, 2))))


if __name__ == "__main__":
    main()
