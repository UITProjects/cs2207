"""Plotly figures over the Erangel map (meters, origin top-left, y reversed, square)."""
from __future__ import annotations

import base64
from functools import lru_cache

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy.spatial import ConvexHull, QhullError

from src.config import ROOT

MAP_M = 8160.0
TEAM_COLORS = ["#e6194B", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4", "#42d4f4", "#f032e6", "#bfef45",
               "#fabed4", "#469990", "#dcbeff", "#9A6324", "#fffac8", "#800000", "#aaffc3", "#808000", "#ffd8b1",
               "#000075", "#a9a9a9", "#ffffff", "#ff7f50", "#7fffd4", "#d2691e", "#6495ed"]
CLUSTER_COLORS = ["#ff595e", "#ffca3a", "#8ac926", "#1982c4", "#6a4c93", "#ff924c", "#52a675", "#c5ca30",
                  "#4267ac", "#b5a6c9", "#f15bb5", "#00bbf9", "#00f5d4", "#fee440", "#9b5de5"]
NOISE = "rgba(200,200,200,0.55)"


@lru_cache(maxsize=1)
def map_source() -> str:
    raw = (ROOT / "assets/maps/erangel_1024.jpg").read_bytes()
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode()


def team_color(team: str) -> str:
    return TEAM_COLORS[(int(team[1:]) - 1) % len(TEAM_COLORS)]


def base_map(height: int = 640, view: tuple[float, float, float, float] | None = None) -> go.Figure:
    """Empty figure with the map image under data in meters. view = (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = view or (0, 0, MAP_M, MAP_M)
    fig = go.Figure()
    fig.add_layout_image(source=map_source(), xref="x", yref="y", x=0, y=0, sizex=MAP_M, sizey=MAP_M,
                         sizing="stretch", layer="below", opacity=1.0)
    fig.update_xaxes(range=[x0, x1], showgrid=False, zeroline=False, constrain="domain", title=None)
    fig.update_yaxes(range=[y1, y0], showgrid=False, zeroline=False, scaleanchor="x", scaleratio=1, title=None)
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=30, b=0), plot_bgcolor="#0b2a3a",
                      legend=dict(bgcolor="rgba(255,255,255,0.75)", font=dict(size=10)), dragmode="pan")
    return fig


def zoom_box(cx: float, cy: float, r: float, pad: float = 1.6, min_half: float = 350) -> tuple[float, ...]:
    h = max(r * pad, min_half)
    return (cx - h, cy - h, cx + h, cy + h)


def circle(cx: float, cy: float, r: float, color: str, dash: str = "solid", width: float = 2) -> dict:
    return dict(type="circle", xref="x", yref="y", x0=cx - r, y0=cy - r, x1=cx + r, y1=cy + r,
                line=dict(color=color, width=width, dash=dash), layer="above")


def zone_shapes(zones: pd.DataFrame, t: float) -> list[dict]:
    if zones is None or zones.empty:
        return []
    i = max(int(np.searchsorted(zones["t"].to_numpy(), t, side="right")) - 1, 0)
    z = zones.iloc[i]
    out = [circle(z.safe_x, z.safe_y, z.safe_r, "#4aa3ff", width=2.5)]
    if z.warn_r < 0.98 * z.safe_r or abs(z.warn_x - z.safe_x) > 1:
        out.append(circle(z.warn_x, z.warn_y, z.warn_r, "white", dash="dash"))
    return out


def hull_xy(pts: np.ndarray, pad: float = 15.0) -> tuple[list[float], list[float]]:
    if len(pts) >= 3:
        try:
            h = ConvexHull(pts)
            v = pts[h.vertices]
            c = v.mean(axis=0)
            v = v + (v - c) / np.maximum(np.linalg.norm(v - c, axis=1, keepdims=True), 1e-6) * pad
            return list(v[:, 0]) + [v[0, 0]], list(v[:, 1]) + [v[0, 1]]
        except QhullError:
            pass
    c = pts.mean(axis=0)
    a = np.linspace(0, 2 * np.pi, 13)
    return list(c[0] + pad * 2 * np.cos(a)), list(c[1] + pad * 2 * np.sin(a))


def hull_trace(pts: np.ndarray, color: str, name: str = "", opacity: float = 0.25, show: bool = False,
               width: float = 1.5) -> go.Scatter:
    x, y = hull_xy(pts)
    return go.Scatter(x=x, y=y, mode="lines", fill="toself", line=dict(color=color, width=width), opacity=opacity,
                      name=name, showlegend=show, hoverinfo="name")


def fmt_t(t: float) -> str:
    t = int(round(t))
    return f"{t // 60:02d}:{t % 60:02d}"


def trajectories(pos: pd.DataFrame, height: int = 700) -> go.Figure:
    fig = base_map(height)
    for team, g in pos.groupby("team"):
        xs, ys = [], []
        for _, p in g.groupby("player"):
            p = p.sort_values("t")
            gap = p["t"].diff().fillna(0) > 10.5
            for x, y, br in zip(p["x"], p["y"], gap, strict=True):
                if br:
                    xs.append(None)
                    ys.append(None)
                xs.append(x)
                ys.append(y)
            xs.append(None)
            ys.append(None)
        fig.add_trace(go.Scattergl(x=xs, y=ys, mode="lines", line=dict(color=team_color(team), width=1.4), opacity=0.6,
                                   name=team, hoverinfo="name"))
    return fig


def animation(pos: pd.DataFrame, zones: pd.DataFrame | None, times: list[int] | None = None, max_frames: int = 300,
              highlight: set[str] | None = None, view=None, height: int = 680, color_by: str = "team",
              frame_ms: int = 220) -> go.Figure:
    """Time animation (Play + slider). Players coloured by team; `highlight` players get a thick outline."""
    times = sorted(pos["t"].unique()) if times is None else times
    if len(times) > max_frames:
        step = int(np.ceil(len(times) / max_frames))
        times = times[::step]
    by_t = {t: g for t, g in pos.groupby("t")}
    hl = highlight or set()

    def data_at(t):
        g = by_t.get(t, pos.iloc[0:0])
        colors = [team_color(tm) for tm in g["team"]] if color_by == "team" else list(g["color"])
        lw = [3 if p in hl else 0.6 for p in g["player"]]
        lc = ["black" if p in hl else "white" for p in g["player"]]
        return go.Scatter(x=g["x"], y=g["y"], mode="markers", text=g["player"] + " · " + g["team"],
                          hoverinfo="text", marker=dict(size=9 if hl else 7, color=colors, line=dict(width=lw, color=lc)),
                          showlegend=False)

    fig = base_map(height, view)
    t0 = times[0] if times else 0
    fig.add_trace(data_at(t0))
    fig.update_layout(shapes=zone_shapes(zones, t0), title=f"t = {fmt_t(t0)}")
    fig.frames = [go.Frame(data=[data_at(t)], name=str(t),
                           layout=go.Layout(shapes=zone_shapes(zones, t), title=f"t = {fmt_t(t)}")) for t in times]
    fig.update_layout(
        updatemenus=[dict(type="buttons", showactive=False, x=0.01, y=0.01, xanchor="left", yanchor="bottom",
                          buttons=[dict(label="▶ Play", method="animate",
                                        args=[None, dict(frame=dict(duration=frame_ms, redraw=True), fromcurrent=True,
                                                         transition=dict(duration=0))]),
                                   dict(label="⏸", method="animate",
                                        args=[[None], dict(frame=dict(duration=0, redraw=False), mode="immediate")])])],
        sliders=[dict(active=0, y=-0.02, len=0.9, x=0.08, currentvalue=dict(prefix="t = "),
                      steps=[dict(label=fmt_t(t), method="animate",
                                  args=[[str(t)], dict(mode="immediate", frame=dict(duration=0, redraw=True))])
                             for t in times])])
    return fig
