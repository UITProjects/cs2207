"""Symmetric Hausdorff distance between two point sets, with a cheap bounding-box lower bound.

Lower bound (used for pruning in crowd discovery): for point sets A, B,
    d_H(A, B) >= max(|minx_A - minx_B|, |maxx_A - maxx_B|, |miny_A - miny_B|, |maxy_A - maxy_B|).
Proof for minx: if minx_A < minx_B, the left-most point of A is at least minx_B - minx_A away from
every point of B (and symmetrically). So when the bound already exceeds δ, d_H > δ and the exact
distance is never computed.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial.distance import directed_hausdorff


def hausdorff(A: np.ndarray, B: np.ndarray) -> float:
    return float(max(directed_hausdorff(A, B)[0], directed_hausdorff(B, A)[0]))


def bbox_lower_bound(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    return float(max(abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2]), abs(a[3] - b[3])))
