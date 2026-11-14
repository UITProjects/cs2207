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


def labeler(labels: dict[str, str] | None):
    """id → display label (team tag / player name), falling back to the id."""
    labels = labels or {}
    return lambda x: labels.get(x, x)


def who(df: pd.DataFrame, labels: dict[str, str] | None) -> pd.Series:
    """'Baren · MiTH' (or 'P017 · T05') hover text per position row."""
    L = labeler(labels)
    return df["player"].map(L) + " · " + df["team"].map(L)


def team_color(team: str) -> str:
    return TEAM_COLORS[(int(team[1:]) - 1) % len(TEAM_COLORS)]


def base_map(height: int = 640, view: tuple[float, float, float, float] | None = None, dim: float = 0.0) -> go.Figure:
    """Empty figure with the map image under data in meters. view = (x0, y0, x1, y1).
    dim in [0, 1) darkens the map (image opacity 1 - dim over a dark background) so lines stand out."""
    x0, y0, x1, y1 = view or (0, 0, MAP_M, MAP_M)
    fig = go.Figure()
    fig.add_layout_image(source=map_source(), xref="x", yref="y", x=0, y=0, sizex=MAP_M, sizey=MAP_M,
                         sizing="stretch", layer="below", opacity=1.0 - dim)
    fig.update_xaxes(range=[x0, x1], showgrid=False, zeroline=False, constrain="domain", title=None)
    fig.update_yaxes(range=[y1, y0], showgrid=False, zeroline=False, scaleanchor="x", scaleratio=1, title=None)
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=30, b=0), plot_bgcolor="#05121a" if dim else "#0b2a3a",
                      legend=dict(bgcolor="rgba(255,255,255,0.75)", font=dict(size=10)), dragmode="pan")
    return fig


# ---------------- team movement (one match) ----------------
FOCUS_COLORS = ["#ff3b30", "#2f8cff", "#ffd60a", "#34c759"]
OTHER_COLORS = ["#ff924c", "#c77dff", "#00f5d4", "#f15bb5", "#c5ca30", "#a0c4ff", "#ffadad", "#bdb2ff",
                "#9bf6ff", "#fdffb6", "#caffbf", "#ffc6ff"]
GREY = "rgba(235,235,235,0.55)"
TEXT_SHADOW = "1px 1px 2px black, -1px -1px 2px black"


def place_labels(fig: go.Figure, size: int = 10) -> None:
    """Small white place names (assets/erangel_places.yaml) on top of the map."""
    from src.analytics.gazetteer import places

    ps = places()
    fig.add_trace(go.Scatter(x=[p["x"] for p in ps], y=[p["y"] for p in ps], mode="text",
                             text=[p["name"] for p in ps], hoverinfo="skip", showlegend=False,
                             textfont=dict(color="rgba(255,255,255,0.85)", size=size, shadow=TEXT_SHADOW)))


def _broken_line(df: pd.DataFrame, gap: float = 10.5) -> tuple[list, list]:
    """x/y lists with None where consecutive rows are more than `gap` seconds apart."""
    xs: list = []
    ys: list = []
    prev = None
    for t, x, y in zip(df["t"], df["x"], df["y"], strict=True):
        if prev is not None and t - prev > gap:
            xs.append(None)
            ys.append(None)
        xs.append(x)
        ys.append(y)
        prev = t
    return xs, ys


def team_routes(tracks: pd.DataFrame, summary: pd.DataFrame, focus: list[str], colors: dict[str, str],
                zones: pd.DataFrame | None = None, height: int = 760, tick_s: int = 180,
                labels: dict[str, str] | None = None) -> go.Figure:
    """Squad-centre path of every team: grey for the others, thick colour for `focus` teams with a start
    marker (● landing), an end marker (■ end of trajectory) and time ticks every `tick_s` seconds."""
    fig = base_map(height, dim=0.45)
    place_labels(fig)
    xs, ys = [], []
    for team, tr in tracks.groupby("team"):
        if team in focus:
            continue
        x, y = _broken_line(tr)
        xs += x + [None]
        ys += y + [None]
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=GREY, width=1.5), name="các đội khác",
                             hoverinfo="skip"))
    info = summary.set_index("team")
    for team in focus:
        tr = tracks[tracks["team"] == team]
        if tr.empty:
            continue
        col = colors[team]
        r = info.loc[team]
        x, y = _broken_line(tr)
        tn = labeler(labels)(team)
        fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color=col, width=4), name=tn, hoverinfo="name"))
        ticks = tr[(tr["t"] % tick_s) < 10]
        keep, last = [], None  # skip a tick that would sit on top of the previous one (team standing still)
        for i, rr in ticks.iterrows():
            if last is None or np.hypot(rr.x - last[0], rr.y - last[1]) > 250:
                keep.append(i)
                last = (rr.x, rr.y)
        ticks = ticks.loc[keep]
        fig.add_trace(go.Scatter(x=ticks["x"], y=ticks["y"], mode="markers+text", showlegend=False,
                                 marker=dict(size=6, color=col, line=dict(width=1, color="black")),
                                 text=[fmt_t(t) for t in ticks["t"]], textposition="top right",
                                 textfont=dict(color="white", size=9, shadow=TEXT_SHADOW),
                                 hovertext=[f"{tn} · {fmt_t(t)}" for t in ticks["t"]], hoverinfo="text"))
        a, b = tr.iloc[0], tr.iloc[-1]
        fig.add_trace(go.Scatter(x=[a.x], y=[a.y], mode="markers", showlegend=False, hoverinfo="text",
                                 hovertext=f"{tn} tiếp đất {fmt_t(a.t)} · {r['land_place']}",
                                 marker=dict(size=15, color=col, symbol="circle", line=dict(width=2.5, color="white"))))
        fig.add_trace(go.Scatter(x=[b.x], y=[b.y], mode="markers", showlegend=False, hoverinfo="text",
                                 hovertext=f"{tn} kết thúc quỹ đạo {fmt_t(r['end_t'])} · {r['end_place']}",
                                 marker=dict(size=13, color=col, symbol="square", line=dict(width=2, color="white"))))
    if zones is not None and len(zones):
        z = zones.iloc[-1]
        fig.update_layout(shapes=[circle(z.safe_x, z.safe_y, z.safe_r, "#4aa3ff", dash="dot", width=2)])
    fig.update_layout(legend=dict(orientation="h", y=1.0, x=0, yanchor="bottom", bgcolor="rgba(255,255,255,0.85)",
                                  font=dict(size=12)), margin=dict(l=0, r=0, t=40, b=0))
    return fig


def _play_controls(fig: go.Figure, times: list, frame_ms: int) -> None:
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


def replay(pos: pd.DataFrame, zones: pd.DataFrame | None, focus: list[str], colors: dict[str, str],
           labels: dict[str, str] | None = None, trail_steps: int = 6, follow: str | None = None, follow_half: float = 700,
           height: int = 760, frame_ms: int = 250, max_frames: int = 300) -> go.Figure:
    """Animated replay: other players as small grey dots, focus teams as big coloured dots with a tail of
    the last `trail_steps` positions. `follow` keeps the view on one team."""
    counts = pos.groupby("t").size()
    start = counts.index[counts >= 0.5 * counts.max()].min() if len(counts) else 0  # skip the near-empty drop
    times = [t for t in sorted(pos["t"].unique()) if t >= start]
    if len(times) > max_frames:
        times = times[:: int(np.ceil(len(times) / max_frames))]
    dt = float(np.median(np.diff(times))) if len(times) > 1 else 10.0
    by_t = {t: g for t, g in pos.groupby("t")}
    fpos = pos[pos["team"].isin(focus)].sort_values(["player", "t"])
    centre = pos[pos["team"] == follow].groupby("t")[["x", "y"]].mean() if follow else None

    def frame_data(t):
        g = by_t.get(t, pos.iloc[0:0])
        o = g[~g["team"].isin(focus)]
        out = [go.Scatter(x=o["x"], y=o["y"], mode="markers", hoverinfo="text", text=who(o, labels),
                          marker=dict(size=6, color="rgba(235,235,235,0.75)", line=dict(width=0.5, color="black")),
                          showlegend=False)]
        win = fpos[(fpos["t"] > t - trail_steps * dt - 0.5) & (fpos["t"] <= t)]
        for team in focus:
            w = win[win["team"] == team]
            xs, ys = [], []
            for _, p in w.groupby("player"):
                x, y = _broken_line(p, gap=dt + 0.5)
                xs += x + [None]
                ys += y + [None]
            out.append(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=colors[team], width=3), opacity=0.6,
                                  hoverinfo="skip", showlegend=False))
            now = g[g["team"] == team]
            out.append(go.Scatter(x=now["x"], y=now["y"], mode="markers", hoverinfo="text",
                                  text=who(now, labels), showlegend=False,
                                  marker=dict(size=12, color=colors[team], line=dict(width=1.5, color="white"))))
        return out

    last_view = [None]

    def frame_layout(t) -> dict:
        lay = dict(shapes=zone_shapes(zones, t), title=f"t = {fmt_t(t)} · {len(by_t.get(t, []))} người")
        if centre is not None and len(centre):
            if t in centre.index:
                c = centre.loc[t]
                last_view[0] = zoom_box(c.x, c.y, follow_half, pad=1.0, min_half=follow_half)
            v = last_view[0] or zoom_box(*centre.iloc[0], follow_half, pad=1.0, min_half=follow_half)
            lay["xaxis"] = dict(range=[v[0], v[2]])
            lay["yaxis"] = dict(range=[v[3], v[1]])
        return lay

    fig = base_map(height, dim=0.3)
    place_labels(fig, size=11)
    n_static = len(fig.data)
    t0 = times[0] if times else 0
    for tr in frame_data(t0):
        fig.add_trace(tr)
    fig.update_layout(**frame_layout(t0))
    idx = list(range(n_static, len(fig.data)))
    fig.frames = [go.Frame(data=frame_data(t), traces=idx, name=str(t), layout=go.Layout(**frame_layout(t)))
                  for t in times]
    _play_controls(fig, times, frame_ms)
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


def animation(pos: pd.DataFrame, zones: pd.DataFrame | None, times: list[int] | None = None, max_frames: int = 300,
              labels: dict[str, str] | None = None,
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
        return go.Scatter(x=g["x"], y=g["y"], mode="markers", text=who(g, labels),
                          hoverinfo="text", marker=dict(size=9 if hl else 7, color=colors, line=dict(width=lw, color=lc)),
                          showlegend=False)

    fig = base_map(height, view)
    t0 = times[0] if times else 0
    fig.add_trace(data_at(t0))
    fig.update_layout(shapes=zone_shapes(zones, t0), title=f"t = {fmt_t(t0)}")
    fig.frames = [go.Frame(data=[data_at(t)], name=str(t),
                           layout=go.Layout(shapes=zone_shapes(zones, t), title=f"t = {fmt_t(t)}")) for t in times]
    _play_controls(fig, times, frame_ms)
    return fig
