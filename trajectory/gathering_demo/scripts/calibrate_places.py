"""Visual calibration of assets/erangel_places.yaml: draws every place (circle = radius) and the
bridges on the map → PNG. Edit the YAML, re-run, repeat until labels sit on the towns.

    uv run python scripts/calibrate_places.py [-o places.png] [--grid 500]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from PIL import Image  # noqa: E402

from src.analytics.gazetteer import places  # noqa: E402
from src.config import path  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="places_calibration.png")
    ap.add_argument("--grid", type=int, default=500, help="grid spacing in meters (0 = none)")
    a = ap.parse_args()
    fig, ax = plt.subplots(figsize=(12, 12))
    ax.imshow(Image.open(path("map_image")), extent=(0, 8160, 8160, 0))
    if a.grid:
        for v in range(0, 8161, a.grid):
            ax.axhline(v, color="white", lw=0.3, alpha=0.4)
            ax.axvline(v, color="white", lw=0.3, alpha=0.4)
    for p in places():
        col = {"hot": "red", "town": "yellow", "bridge": "cyan"}.get(p["kind"], "white")
        ax.add_patch(plt.Circle((p["x"], p["y"]), p["r"], fill=False, color=col, lw=1.2))
        ax.text(p["x"], p["y"], p["name"], color=col, fontsize=8, ha="center", va="center")
        if p["kind"] == "bridge":
            ax.plot([p["x1"], p["x2"]], [p["y1"], p["y2"]], color="cyan", lw=2)
    ax.set_xlim(0, 8160)
    ax.set_ylim(8160, 0)
    fig.savefig(a.out, dpi=90, bbox_inches="tight")
    print(a.out)


if __name__ == "__main__":
    main()
