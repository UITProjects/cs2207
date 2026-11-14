"""Quick PNG of one raw match over the map (plausibility check of the mock or a real match).

    uv run python scripts/plot_match.py data/raw/mock/mock-2207-0000 [-o out.png]
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from PIL import Image  # noqa: E402

from src.config import path  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("match_dir")
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()
    d = Path(a.match_dir)
    ev = json.load(gzip.open(d / "telemetry.json.gz", "rt", encoding="utf8"))
    tracks: dict[str, list] = {}
    team: dict[str, int] = {}
    for e in ev:
        if e["_T"] == "LogPlayerPosition" and e["character"]["location"]["z"] < 100000:
            c = e["character"]
            tracks.setdefault(c["accountId"], []).append((c["location"]["x"] / 100, c["location"]["y"] / 100))
            team[c["accountId"]] = c["teamId"]
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.imshow(Image.open(path("map_image")), extent=(0, 8160, 8160, 0))
    cmap = plt.get_cmap("tab20")
    for acc, pts in tracks.items():
        xs, ys = zip(*pts, strict=True)
        ax.plot(xs, ys, "-", lw=0.8, alpha=0.6, color=cmap(team[acc] % 20))
    kills = [e for e in ev if e["_T"] == "LogPlayerKillV2"]
    ax.scatter([k["victim"]["location"]["x"] / 100 for k in kills], [k["victim"]["location"]["y"] / 100 for k in kills],
               marker="x", c="red", s=18, label="eliminations")
    gt = d / "ground_truth.json"
    if gt.exists():
        for g in json.loads(gt.read_text())["gatherings"]:
            ax.add_patch(plt.Circle(g["center"], g["radius"], fill=False, color="yellow", lw=1.5))
            ax.text(g["center"][0], g["center"][1], f'{g["kind"]}\n{g["t_start"]:.0f}-{g["t_end"]:.0f}s', color="yellow",
                    fontsize=7)
    ax.set_xlim(0, 8160)
    ax.set_ylim(8160, 0)
    ax.legend(loc="lower left")
    out = a.out or str(d / "plot.png")
    fig.savefig(out, dpi=80, bbox_inches="tight")
    print(out)


if __name__ == "__main__":
    main()
