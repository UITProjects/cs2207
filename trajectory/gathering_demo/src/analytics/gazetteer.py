"""Nearest named place for a point (assets/erangel_places.yaml; coordinates are estimates)."""
from __future__ import annotations

import math
from functools import lru_cache

import yaml

from src.config import path


@lru_cache(maxsize=1)
def places() -> list[dict]:
    with open(path("places"), encoding="utf8") as f:
        return yaml.safe_load(f)["places"]


def nearest_place(x: float, y: float, max_dist: float = 1200.0) -> str:
    """Name of the nearest place; bridges win when the point lies within their radius.
    Beyond max_dist from any place: 'gần <name>' style label."""
    best, bd = None, float("inf")
    for p in places():
        d = math.hypot(x - p["x"], y - p["y"])
        if p["kind"] == "bridge" and d <= p["r"]:
            return p["name"]
        if d - p["r"] < bd:
            best, bd = p, d - p["r"]
    if best is None:
        return "?"
    return best["name"] if bd <= max_dist else f"~{best['name']}"
