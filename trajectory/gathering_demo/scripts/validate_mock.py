"""Precision / recall of detected gatherings vs the mock ground truth (data/raw/mock/*/ground_truth.json).

A ground-truth gathering is recalled when a detected gathering overlaps it in time with IoU ≥ 0.3 and
its centroid lies within the ground-truth area (radius + eps). Precision counts detected gatherings
matching any ground-truth item; unscripted (emergent) gatherings lower it, so recall is the target.

    uv run python scripts/validate_mock.py [--n 50] [--param delta=300 ...]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import default_params, path  # noqa: E402
from src.mining.pipeline import run_pipeline  # noqa: E402
from src.parse.telemetry import read_tables  # noqa: E402

IOU_MIN = 0.3


def iou(a0, a1, b0, b1) -> float:
    inter = max(0.0, min(a1, b1) - max(a0, b0))
    union = max(a1, b1) - min(a0, b0)
    return inter / union if union > 0 else float(a0 == b0)


def evaluate(n: int, params: dict, verbose: bool = True) -> dict:
    proc = path("processed") / "mock"
    dirs = sorted(d for d in proc.iterdir() if (d / "meta.json").exists())[:n]
    tp_gt, tot_gt, tp_det, tot_det, times = Counter(), Counter(), 0, 0, []
    for d in dirs:
        gt_file = path("raw") / "mock" / d.name / "ground_truth.json"
        if not gt_file.exists():
            continue
        gt = json.loads(gt_file.read_text())["gatherings"]
        s = time.time()
        res = run_pipeline(read_tables(d), params)
        times.append(time.time() - s)
        det = res.gathering_df
        hit = np.zeros(len(det), bool)
        for g in gt:
            tot_gt[g["kind"]] += 1
            ok = False
            for i, r in enumerate(det.itertuples()):
                close = np.hypot(r.cx - g["center"][0], r.cy - g["center"][1]) <= g["radius"] + params["eps"]
                if close and iou(r.t_start, r.t_end, g["t_start"], g["t_end"]) >= IOU_MIN:
                    ok, hit[i] = True, True
            tp_gt[g["kind"]] += ok
        tp_det += int(hit.sum())
        tot_det += len(det)
    rec = sum(tp_gt.values()) / max(sum(tot_gt.values()), 1)
    prec = tp_det / max(tot_det, 1)
    out = dict(matches=len(times), recall=rec, precision=prec, by_kind={k: (tp_gt[k], tot_gt[k]) for k in tot_gt},
               detected=tot_det, sec_per_match=float(np.mean(times)) if times else 0, max_sec=max(times, default=0))
    if verbose:
        print(f"matches={out['matches']} params={params}")
        for k, (a, b) in out["by_kind"].items():
            print(f"  recall {k:13s} {a:3d}/{b:3d} = {a / max(b, 1):.2f}")
        print(f"RECALL {rec:.3f}   PRECISION {prec:.3f} ({tp_det}/{tot_det} detected gatherings match a scripted one)")
        print(f"runtime {out['sec_per_match']:.2f} s/match (max {out['max_sec']:.2f})")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--param", action="append", default=[])
    a = ap.parse_args()
    p = default_params()
    for kv in a.param:
        k, v = kv.split("=")
        p[k] = type(p[k])(float(v)) if isinstance(p[k], int) else float(v)
    out = evaluate(a.n, p)
    sys.exit(0 if out["recall"] >= 0.8 else 1)


if __name__ == "__main__":
    main()
