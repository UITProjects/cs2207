"""Download processed data from the latest successful `pubg-crawl` GitHub Actions run(s) into
data/processed/pubg/ (needs the `gh` CLI, logged in).

    uv run python scripts/pull_cloud_data.py [--runs 3]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import path  # noqa: E402

WORKFLOW = "pubg-crawl.yml"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1, help="how many recent successful runs to merge")
    a = ap.parse_args()
    if not shutil.which("gh"):
        sys.exit("gh CLI not found: https://cli.github.com/ (then `gh auth login`)")
    runs = json.loads(subprocess.check_output(["gh", "run", "list", "--workflow", WORKFLOW, "--status", "success",
                                               "--limit", str(a.runs), "--json", "databaseId,createdAt"]))
    if not runs:
        sys.exit("no successful pubg-crawl runs yet")
    dest = path("processed") / "pubg"
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for r in runs:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.check_call(["gh", "run", "download", str(r["databaseId"]), "--dir", tmp])
            for meta in Path(tmp).rglob("meta.json"):
                src = meta.parent
                out = dest / src.name
                if not out.exists():
                    shutil.copytree(src, out)
                    n += 1
        print(f"run {r['databaseId']} ({r['createdAt']}) merged")
    print(f"{n} new matches → {dest}. Next: uv run python scripts/build_sample.py --source pubg")


if __name__ == "__main__":
    main()
