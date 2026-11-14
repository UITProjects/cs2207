"""3D space-time cube (x, y, t), like Fig. 1c of the Gathering paper, with the Erangel map on the floor.

`space_time_cube` is the generic renderer; `team_cube` (match page) and `algo_cube` (algorithm page) build
its inputs. Everything is WebGL (Scatter3d / Mesh3d / Surface); discs of the same colour are merged into one
Mesh3d so a window with hundreds of clusters stays a handful of traces.
"""
from __future__ import annotations

from collections import defaultdict
from functools import lru_cache

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from PIL import Image

from src.config import ROOT
from src.viz.map_plot import MAP_M, fmt_t, hull_xy, labeler, zoom_box

FULL = (0.0, 0.0, MAP_M, MAP_M)
N_COLORS = 48
ORANGE, BLUE, PALE, DARK = "#E08A4F", "#2D5F9A", "#C9C3B5", "#5A6070"
CROWD_COLORS = ["#E08A4F", "#2D5F9A", "#8ac926", "#c77dff", "#ff595e", "#00bbf9", "#f15bb5", "#c5ca30"]


# ---------------- map floor ----------------
@lru_cache(maxsize=1)
def _map_image() -> Image.Image:
    return Image.open(ROOT / "assets/maps/erangel.jpg").convert("RGB")


@lru_cache(maxsize=32)
def _floor(view: tuple[int, int, int, int], res: int):
    """Surface colours must interpolate smoothly between vertices, so the scalar is the pixel brightness and the
    colour scale is the mean map colour of each brightness band (water stays blue, land stays green/grey)."""
    im = _map_image()
    s = im.width / MAP_M
    x0, y0, x1, y1 = (max(view[0], 0), max(view[1], 0), min(view[2], MAP_M), min(view[3], MAP_M))
    crop = im.crop((round(x0 * s), round(y0 * s), round(x1 * s), round(y1 * s))).resize((res, res), Image.BILINEAR)
    rgb = np.asarray(crop, dtype=float)
    lum = rgb @ np.array([0.299, 0.587, 0.114])
    edges = np.quantile(lum, np.linspace(0, 1, N_COLORS + 1))
    band = np.clip(np.searchsorted(edges, lum, side="right") - 1, 0, N_COLORS - 1)
    flat, fb = rgb.reshape(-1, 3), band.ravel()
    scale = []
    for i in range(N_COLORS):
        m = flat[fb == i]
        c = m.mean(axis=0) if len(m) else np.array([lum.mean()] * 3)
        scale.append([i / (N_COLORS - 1), f"rgb({int(c[0])},{int(c[1])},{int(c[2])})"])
    # scalar = band position with a fractional part from the brightness inside the band (continuous, monotonic)
    lo, hi = edges[band], edges[np.minimum(band + 1, N_COLORS)]
    frac = np.where(hi > lo, (lum - lo) / np.maximum(hi - lo, 1e-9), 0.0)
    val = np.clip(band + frac, 0, N_COLORS - 1)
    return np.linspace(x0, x1, res), np.linspace(y0, y1, res), val, scale


def map_floor(view: tuple[float, float, float, float], z: float, res: int = 160) -> go.Surface:
    """The map cropped to `view` as a flat textured surface at height z."""
    xs, ys, idx, scale = _floor(tuple(int(round(v)) for v in view), res)
    return go.Surface(x=xs, y=ys, z=np.full(idx.shape, float(z)), surfacecolor=idx, colorscale=scale, cmin=0,
                      cmax=N_COLORS - 1, showscale=False, hoverinfo="skip", name="map",
                      lighting=dict(ambient=1.0, diffuse=0.0, specular=0.0, roughness=1.0, fresnel=0.0),
                      contours=dict(x=dict(highlight=False), y=dict(highlight=False), z=dict(highlight=False)))


# ---------------- generic renderer ----------------
def _tick_step(span: float) -> int:
    for step in (30, 60, 120, 180, 300):
        if span / step <= 10:
            return step
    return 600


def _xyz(df: pd.DataFrame, gap: float = 10.5) -> tuple[list, list, list, list]:
    xs, ys, zs, hv = [], [], [], []
    has_label = "label" in df
    for p, g in df.sort_values(["player", "t"]).groupby("player", sort=False):
        prev = None
        labels = g["label"] if has_label else [None] * len(g)
        for t, x, y, lb in zip(g["t"], g["x"], g["y"], labels, strict=True):
            if prev is not None and t - prev > gap:
                xs.append(None), ys.append(None), zs.append(None), hv.append(None)
            xs.append(x), ys.append(y), zs.append(t), hv.append(lb or f"{p} · {fmt_t(t)}")
            prev = t
        xs.append(None), ys.append(None), zs.append(None), hv.append(None)
    return xs, ys, zs, hv


def _disc_mesh(discs: list[dict], color: str, opacity: float) -> go.Mesh3d:
    X, Y, Z, ii, jj, kk, txt = [], [], [], [], [], [], []
    for d in discs:
        hx, hy = hull_xy(np.asarray(d["pts"], dtype=float), pad=d.get("pad", 15.0))
        hx, hy = hx[:-1], hy[:-1]  # drop the closing vertex
        n = len(hx)
        c = len(X)
        X += [float(np.mean(hx))] + list(hx)
        Y += [float(np.mean(hy))] + list(hy)
        Z += [d["t"]] * (n + 1)
        txt += [d.get("hover", "")] * (n + 1)
        for j in range(n):
            ii.append(c)
            jj.append(c + 1 + j)
            kk.append(c + 1 + (j + 1) % n)
    return go.Mesh3d(x=X, y=Y, z=Z, i=ii, j=jj, k=kk, color=color, opacity=opacity, flatshading=True,
                     hovertext=txt, hoverinfo="text", showscale=False, showlegend=False,
                     lighting=dict(ambient=0.9, diffuse=0.2, specular=0.0))


def space_time_cube(view: tuple[float, float, float, float], t_lo: float, t_hi: float, lines: list[dict] = (),
                    discs: list[dict] = (), links: list[dict] = (), points: list[dict] = (), labels: list[dict] = (),
                    planes_at: list[float] = (), height: int = 640, floor: bool = True,
                    rev: str = "cube") -> go.Figure:
    """x/y in meters (y reversed like the map), z = t in seconds.
    lines:  {df(player,t,x,y), color, width, name, markers, opacity, legend}
    discs:  {pts (n,2), t, color, opacity, hover}      → one Mesh3d per (color, opacity)
    links:  {a:(x,y,t), b:(x,y,t), color, hover, dash} → dashed segments
    points: {x, y, t, color, symbol, size, hover}      labels: {x, y, t, text, color, size}"""
    x0, y0, x1, y1 = view
    span = max(t_hi - t_lo, 10)
    z_floor = t_lo - 0.02 * span
    fig = go.Figure()
    if floor:
        fig.add_trace(map_floor(view, z_floor))
    if planes_at:
        px, py, pz = [], [], []
        for t in planes_at:
            px += [x0, x1, x1, x0, x0, None]
            py += [y0, y0, y1, y1, y0, None]
            pz += [t] * 5 + [None]
        fig.add_trace(go.Scatter3d(x=px, y=py, z=pz, mode="lines", line=dict(color="rgba(120,120,120,0.35)", width=1),
                                   hoverinfo="skip", showlegend=False))
    for ln in lines:
        if ln["df"].empty:
            continue
        xs, ys, zs, hv = _xyz(ln["df"])
        mk = ln.get("markers", False)
        fig.add_trace(go.Scatter3d(x=xs, y=ys, z=zs, mode="lines+markers" if mk else "lines", name=ln.get("name", ""),
                                   line=dict(color=ln["color"], width=ln.get("width", 2), dash=ln.get("dash", "solid")),
                                   opacity=ln.get("opacity", 1), legendgroup=ln.get("group"),
                                   marker=dict(size=ln.get("marker_size", 2), color=ln["color"]),
                                   hovertext=hv, hoverinfo="text", showlegend=ln.get("legend", False),
                                   connectgaps=False))
    groups: dict[tuple, list] = defaultdict(list)
    for d in discs:
        groups[(d["color"], d.get("opacity", 0.4))].append(d)
    for (col, op), ds in groups.items():
        fig.add_trace(_disc_mesh(ds, col, op))
    lg: dict[tuple, list] = defaultdict(list)
    for lk in links:
        lg[(lk["color"], lk.get("dash", "dash"))].append(lk)
    for (col, dash), ls in lg.items():
        xs, ys, zs, hv = [], [], [], []
        for lk in ls:
            for p in (lk["a"], lk["b"]):
                xs.append(p[0]), ys.append(p[1]), zs.append(p[2]), hv.append(lk.get("hover", ""))
            xs.append(None), ys.append(None), zs.append(None), hv.append(None)
        fig.add_trace(go.Scatter3d(x=xs, y=ys, z=zs, mode="lines", line=dict(color=col, width=6, dash=dash),
                                   hovertext=hv, hoverinfo="text", showlegend=False))
    for p in points:
        fig.add_trace(go.Scatter3d(x=[p["x"]], y=[p["y"]], z=[p["t"]], mode="markers", showlegend=False,
                                   marker=dict(size=p.get("size", 6), color=p["color"], symbol=p.get("symbol", "circle"),
                                               line=dict(width=2, color="white")),
                                   hovertext=[p.get("hover", "")], hoverinfo="text"))
    if labels:
        fig.add_trace(go.Scatter3d(x=[lb["x"] for lb in labels], y=[lb["y"] for lb in labels],
                                   z=[lb["t"] for lb in labels], mode="text", text=[lb["text"] for lb in labels],
                                   textfont=dict(color=[lb.get("color", "#172033") for lb in labels],
                                                 size=[lb.get("size", 12) for lb in labels]),
                                   hoverinfo="skip", showlegend=False))
    step = _tick_step(span)
    ticks = list(range(int(np.ceil(t_lo / step) * step), int(t_hi) + 1, step))
    fig.update_layout(
        height=height, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", uirevision=rev,
        legend=dict(orientation="h", y=1.0, x=0, bgcolor="rgba(255,255,255,0.8)"),
        scene=dict(
            xaxis=dict(title="x (m)", range=[x0, x1], showbackground=False, gridcolor="#D8D0BE"),
            yaxis=dict(title="y (m)", range=[y1, y0], showbackground=False, gridcolor="#D8D0BE"),
            # the z "background" is the floor plane of the box: keep it off and below the map to avoid z-fighting
            zaxis=dict(title="t", range=[z_floor - 0.03 * span, t_hi + 0.03 * span], tickvals=ticks,
                       ticktext=[fmt_t(t) for t in ticks], showbackground=False, gridcolor="#D8D0BE"),
            aspectmode="manual", aspectratio=dict(x=1, y=1, z=0.9),
            camera=dict(eye=dict(x=0.35, y=-1.85, z=0.95), center=dict(x=0, y=0, z=-0.12)),  # from the south
            uirevision=rev))
    return fig


# ---------------- match page ----------------
def team_cube(tracks: pd.DataFrame, summary: pd.DataFrame, focus: list[str], colors: dict[str, str],
              gathering_df: pd.DataFrame | None, clusters: list, t_range: tuple[float, float],
              show_others: bool = True, show_gatherings: bool = True, height: int = 720,
              labels: dict[str, str] | None = None) -> go.Figure:
    """Team centre tracks in (x, y, t); focus teams thick and coloured (● start, ■ end of trajectory),
    gatherings as orange disc columns."""
    t_lo, t_hi = t_range
    L = labeler(labels)
    tr = tracks[tracks["t"].between(t_lo, t_hi)].rename(columns={"team": "player"})
    tr = tr.assign(label=[f"{L(tm)} · {fmt_t(t)}" for tm, t in zip(tr["player"], tr["t"], strict=True)])
    lines = []
    if show_others:
        lines.append(dict(df=tr[~tr["player"].isin(focus)], color="#6B7080", width=2, opacity=0.45,
                          name="các đội khác", legend=True))
    info = summary.set_index("team")
    points = []
    for tm in focus:
        d = tr[tr["player"] == tm]
        lines.append(dict(df=d, color=colors[tm], width=8, name=L(tm), legend=True))
        if d.empty:
            continue
        a, b = d.iloc[0], d.iloc[-1]
        if a.t == info.loc[tm, "land_t"]:
            points.append(dict(x=a.x, y=a.y, t=a.t, color=colors[tm], symbol="circle", size=7,
                               hover=f"{L(tm)} tiếp đất {fmt_t(a.t)} · {info.loc[tm, 'land_place']}"))
        if b.t == info.loc[tm, "end_t"]:
            points.append(dict(x=b.x, y=b.y, t=b.t, color=colors[tm], symbol="square", size=7,
                               hover=f"{L(tm)} kết thúc quỹ đạo {fmt_t(b.t)} · {info.loc[tm, 'end_place']}"))
    discs, labels = [], []
    if show_gatherings and gathering_df is not None and len(gathering_df):
        for g in gathering_df.itertuples():
            cs = [clusters[c] for c in g.clusters if t_lo <= clusters[c].t <= t_hi]
            if not cs:
                continue
            name = f"G{g.id + 1} · {getattr(g, 'place', '')}"
            r = max(float(g.radius), 150.0)
            ring = np.c_[np.cos(np.linspace(0, 2 * np.pi, 24, endpoint=False)),
                         np.sin(np.linspace(0, 2 * np.pi, 24, endpoint=False))] * r
            discs += [dict(pts=ring + np.array(c.centroid), t=c.t, color=ORANGE, opacity=0.3, pad=0,
                           hover=f"{name} · {fmt_t(c.t)} · {c.size} người") for c in cs]
            top = cs[-1]
            labels.append(dict(x=top.centroid[0], y=top.centroid[1], t=top.t + 30, text=f"<b>{name}</b>",
                               color="#8A3F14", size=12))
    return space_time_cube(FULL, t_lo, t_hi, lines=lines, discs=discs, points=points, labels=labels, height=height,
                           rev="team_cube")


# ---------------- algorithm page ----------------
def crowd_window(res, crowd_idx: int, pad_steps: int = 3, dt: int = 10) -> tuple[tuple, float, float]:
    """View box (crowd bbox + 250 m) and time span (± pad_steps) around one crowd."""
    cs = [res.clusters[i] for i in res.crowds[crowd_idx]]
    allp = np.vstack([c.pts for c in cs])
    lo, hi = allp.min(0), allp.max(0)
    view = zoom_box(*(lo + hi) / 2, max(hi - lo) / 2 + 250, pad=1.0, min_half=400)
    return view, cs[0].t - pad_steps * dt, cs[-1].t + pad_steps * dt


def _in(df: pd.DataFrame, view, t_lo, t_hi) -> pd.DataFrame:
    return df[df["t"].between(t_lo, t_hi) & df["x"].between(view[0], view[2]) & df["y"].between(view[1], view[3])]


TEAM_PALETTE = ["#e6194B", "#4363d8", "#3cb44b", "#f58231", "#911eb4", "#42d4f4", "#f032e6", "#9A6324",
                "#ffe119", "#000075", "#469990", "#800000", "#bfef45", "#fabed4", "#808000", "#dcbeff"]


def team_palette(teams: list[str]) -> dict[str, str]:
    """High-contrast colour per team, in the given order (cycles after 16)."""
    return {tm: TEAM_PALETTE[i % len(TEAM_PALETTE)] for i, tm in enumerate(teams)}


def window_teams(pos: pd.DataFrame, view, t_lo: float, t_hi: float) -> list[str]:
    """Teams with at least one position inside the view box and time window, sorted."""
    return sorted(_in(pos, view, t_lo, t_hi)["team"].unique())


def _team_centre(df: pd.DataFrame, L=lambda x: x) -> pd.DataFrame:
    """One row per (team, t): mean position of the team's members in df; `player` = team for the line helper."""
    out = df.groupby(["team", "t"], as_index=False).agg(x=("x", "mean"), y=("y", "mean"), n=("player", "nunique"))
    out["player"] = out["team"]
    out["label"] = [f"{L(tm)} · {fmt_t(t)} · {n} người"
                    for tm, t, n in zip(out["team"], out["t"], out["n"], strict=True)]
    return out


def algo_cube(res, pos: pd.DataFrame, mode: str, view, t_lo: float, t_hi: float, crowd_idx: int | None = None,
              show_noise: bool = False, connect: bool = True, height: int = 640, teams: list[str] | None = None,
              by: str = "team", colors: dict[str, str] | None = None,
              labels: dict[str, str] | None = None) -> go.Figure:
    """mode: raw | clusters | crowds | participators — the four algorithm steps in (x, y, t).
    Trajectories are coloured by team (`colors`, default `team_palette`) and limited to `teams`;
    by="team" draws one centre line per team, by="player" one line per player. Discs/links are not filtered."""
    P = res.params
    L = labeler(labels)
    win = _in(pos, view, t_lo, t_hi)
    all_teams = sorted(win["team"].unique())
    colors = colors or team_palette(all_teams)
    keep = all_teams if teams is None else [tm for tm in all_teams if tm in set(teams)]
    shown = [c for c in res.clusters if t_lo <= c.t <= t_hi
             and view[0] <= c.centroid[0] <= view[2] and view[1] <= c.centroid[1] <= view[3]]
    times = sorted(win["t"].unique())
    planes = times if len(times) <= 20 else []
    lines, discs, links = [], [], []

    par: set[str] = set()
    members: set[str] = set()
    if mode == "participators" and crowd_idx is not None:
        td = res.tads[crowd_idx]
        par = set(td["trace"][0]["par"]) if td["trace"] else set()
        members = {m for cid in res.crowds[crowd_idx] for m in res.clusters[cid].members}

    for tm in keep:
        tw = win[win["team"] == tm]
        col = colors.get(tm, "#5A6070")
        n_players = tw["player"].nunique()
        if mode == "participators":
            tw = tw[tw["player"].isin(members)]
            if tw.empty:
                continue
            n_par = int(tw.loc[tw["player"].isin(par), "player"].nunique())
            name = f"{L(tm)} · {n_par} participator" if n_par else f"{L(tm)} · chỉ đi qua"
        else:
            name = f"{L(tm)} · {n_players} người"
        if by == "team":
            solid = mode != "participators" or n_par > 0
            lines.append(dict(df=_team_centre(tw, L), color=col, width=7 if solid else 3, dash="solid" if solid else "dash",
                              name=name, legend=True, group=tm))
            continue
        tw = tw.assign(label=[f"{L(p)} · {L(tm)} · {fmt_t(t)}" for p, t in zip(tw["player"], tw["t"], strict=True)])
        if not connect:  # points only: every point its own segment
            tw = tw.assign(player=tw["player"] + "@" + tw["t"].astype(str))
        if mode == "participators":
            is_par = tw["player"].str.split("@").str[0].isin(par)
            lines.append(dict(df=tw[is_par], color=col, width=7, markers=True, marker_size=3, name=name, legend=True,
                              group=tm))
            lines.append(dict(df=tw[~is_par], color=col, width=2.5, opacity=0.5, markers=True, marker_size=2,
                              name=name, legend=bool(not is_par.any()), group=tm))
        else:
            lines.append(dict(df=tw, color=col, width=2.5, markers=True, marker_size=2, name=name, legend=True,
                              group=tm))
    if show_noise and by == "player" and mode in ("clusters", "crowds"):
        lab = res.labels.merge(win[["player", "t"]], on=["player", "t"])
        nz = lab[lab["cluster"] < 0]
        lines.append(dict(df=nz.assign(player=nz["player"] + "@" + nz["t"].astype(str)), color="#CFCAC0",
                          width=1, markers=True, marker_size=2))

    if mode != "raw":
        crowd_of: dict[int, int] = {}
        for k, cr in enumerate(res.crowds):
            for cid in cr:
                crowd_of.setdefault(cid, k)
        for c in shown:
            big = c.size >= P["m_c"]
            hover = f"c{c.k} · {fmt_t(c.t)} · {c.size} người"
            if mode == "clusters":
                col, op = (DARK, 0.35) if big else (PALE, 0.3)
            elif mode == "crowds":
                k = crowd_of.get(c.id)
                if k is not None and (crowd_idx is None or k == crowd_idx):
                    col, op = "#F3C9A8", 0.45
                    hover += f" · Cr{k + 1}"
                else:
                    col, op = PALE, 0.2
            else:  # participators
                if crowd_idx is None or c.id not in res.crowds[crowd_idx]:
                    continue
                in_g = any(c.id in g for g, _, ci in res.gatherings if ci == crowd_idx)
                col, op = ("#9DBCE0", 0.4) if in_g else (PALE, 0.35)
            discs.append(dict(pts=c.pts, t=c.t, color=col, opacity=op, hover=hover))
        if mode == "crowds":
            ids = {c.id for c in shown}
            for lk in res.links:
                if not lk.close or lk.a not in ids or lk.b not in ids:
                    continue
                a, b = res.clusters[lk.a], res.clusters[lk.b]
                sel = crowd_idx is None or crowd_of.get(lk.a) == crowd_idx
                links.append(dict(a=(*a.centroid, a.t), b=(*b.centroid, b.t), color="#3A3F4B" if sel else "#CFCAC0",
                                  hover=f"d_H = {lk.dH:.0f} m ≤ δ = {P['delta']}" if lk.dH is not None else ""))
    return space_time_cube(view, t_lo, t_hi, lines=lines, discs=discs, links=links, planes_at=planes, height=height,
                           rev=f"algo_{mode}")
