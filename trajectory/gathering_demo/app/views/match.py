"""🎯 Kết quả — các đội di chuyển thế nào và tụ họp (gathering) ở đâu, chỉ từ quỹ đạo (x, y, t)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # app/ (for `common`)
import common  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from common import verdict  # noqa: E402

from src.analytics.movement import MAX_FOCUS, default_focus, team_summary, team_tracks  # noqa: E402
from src.config import default_params  # noqa: E402
from src.viz.cube import ORANGE, space_time_cube, team_cube  # noqa: E402
from src.viz.map_plot import (  # noqa: E402
    FOCUS_COLORS,
    OTHER_COLORS,
    TEXT_SHADOW,
    base_map,
    fmt_t,
    hull_trace,
    place_labels,
    replay,
    team_routes,
    zone_shapes,
    zoom_box,
)

common.page("Kết quả", "🎯")
ctx = common.sidebar(params=False)
P = default_params()
folder, mid = ctx["folder"], ctx["match_id"]
t = common.load_match(folder, mid)
res = common.mine(folder, mid, common.params_key(P))
pos, zones = t["positions"], t["zones"]
gdf = res.gathering_df
T_END = int(pos["t"].max())
labels = ctx["labels"]
LB = tuple(sorted(labels.items()))  # hashable for the figure caches
L = common.label_fn(ctx)


@st.cache_resource(show_spinner=False, max_entries=8)  # read-only, shared
def _summary(folder: str, mid: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    tb = common.load_match(folder, mid)
    r = common.mine(folder, mid, common.params_key(default_params()))
    return team_summary(tb, r.gathering_df), team_tracks(tb["positions"])


@st.cache_resource(show_spinner="Đang dựng replay…", max_entries=8)  # figures: shared, read-only
def _replay(folder: str, mid: str, focus: tuple, follow: str | None, frame_ms: int, lb: tuple = ()) -> go.Figure:
    tb = common.load_match(folder, mid)
    colors = dict(zip(focus, FOCUS_COLORS, strict=False))
    return replay(tb["positions"], tb["zones"], list(focus), colors, labels=dict(lb), follow=follow,
                  frame_ms=frame_ms)


@st.cache_resource(show_spinner="Đang dựng hình 3D…", max_entries=12)  # figures: shared, read-only
def _team_cube(folder: str, mid: str, focus: tuple, t_range: tuple, others: bool, gath: bool,
               lb: tuple = ()) -> go.Figure:
    summary, tracks = _summary(folder, mid)
    r = common.mine(folder, mid, common.params_key(default_params()))
    colors = dict(zip(focus, FOCUS_COLORS, strict=False))
    return team_cube(tracks, summary, list(focus), colors, r.gathering_df, r.clusters, t_range, others, gath,
                     labels=dict(lb))


@st.cache_resource(show_spinner=False, max_entries=12)  # figures: shared, read-only
def _routes(folder: str, mid: str, focus: tuple, lb: tuple) -> go.Figure:
    summary, tracks = _summary(folder, mid)
    colors = dict(zip(focus, FOCUS_COLORS, strict=False))
    return team_routes(tracks, summary, list(focus), colors, common.load_match(folder, mid)["zones"], labels=dict(lb))


summary, tracks = _summary(folder, mid)
info = summary.set_index("team")
gby = {int(r.id): r for r in gdf.itertuples()} if len(gdf) else {}


def gname(gid: int) -> str:
    return f"G{gid + 1} · {gby[gid].place}"


# ---------------- header: data → mining → result ----------------
st.title("🎯 Kết quả: các đội di chuyển và tụ họp ở đâu")
n_teams_g = len({tm for teams in gdf["teams"] for tm in teams}) if len(gdf) else 0
steps = [("", f"{pos['player'].nunique()}", "người chơi"), ("", f"{len(pos) / 1000:.1f}k", "điểm (x, y, t)"),
         ("mine", f"{len(res.clusters)}", "cụm DBSCAN"), ("mine", f"{len(res.crowds)}", "crowd"),
         ("value", f"{len(gdf)}", "gathering"), ("value", f"{n_teams_g}", "đội tham gia gathering")]
html = '<span class="arrow">→</span>'.join(f'<div class="step {c}"><b>{v}</b><span>{lb}</span></div>'
                                            for c, v, lb in steps)
st.markdown(f'<div class="vchain">{html}</div>', unsafe_allow_html=True)
st.page_link("views/algorithm.py", label="← Thuật toán từng bước", icon="🔬")

default = [tm for tm in default_focus(summary) if tm in info.index]
focus = st.multiselect("Đội theo dõi (tối đa 4)", list(summary["team"]), default=default, max_selections=MAX_FOCUS,
                       key=f"focus_{mid}", format_func=L, help="Mặc định: 3 đội tham gia nhiều gathering nhất.")
colors = dict(zip(focus, FOCUS_COLORS, strict=False))


def dot(tm: str) -> str:
    return f'<span style="color:{colors.get(tm, "#888")};font-size:18px">●</span>'


@st.cache_resource(show_spinner=False, max_entries=24)  # figures: shared, read-only
def _enc_fig(folder: str, mid: str, gid: int, mode: str, focus: tuple, lb: tuple, height: int, key: str) -> go.Figure:
    """One gathering in 3D (x, y, t) or 2D, member trajectories coloured by team (focus colours first)."""
    res_ = common.mine(folder, mid, common.params_key(default_params()))
    pos_, zones_ = common.load_match(folder, mid)["positions"], common.load_match(folder, mid)["zones"]
    row = next(r for r in res_.gathering_df.itertuples() if int(r.id) == gid)
    labels_ = dict(lb)
    L_ = lambda x: labels_.get(x, x)  # noqa: E731
    colors_ = dict(zip(focus, FOCUS_COLORS, strict=False))
    cs = [res_.clusters[i] for i in row.clusters]
    allp = np.vstack([cl.pts for cl in cs])
    lo, hi = allp.min(0), allp.max(0)
    view = zoom_box(*(lo + hi) / 2, max(hi - lo) / 2 + 250, pad=1.2, min_half=450)
    t0, t1 = row.t_start - 60, row.t_end + 60
    teams = list(row.teams)
    others_c = iter(OTHER_COLORS * 3)
    tcol = {tm: colors_.get(tm) or next(others_c) for tm in teams}
    win = pos_[pos_["team"].isin(teams) & pos_["t"].between(t0, t1)].sort_values(["player", "t"])
    name = f"G{gid + 1} · {row.place}"
    if mode == "3D":
        lines = [dict(df=win[win["team"] == tm], color=tcol[tm], width=7 if tm in colors_ else 4, name=L_(tm),
                      legend=True) for tm in teams]
        discs = [dict(pts=cl.pts, t=cl.t, color=ORANGE, opacity=0.3, hover=f"{fmt_t(cl.t)} · {cl.size} người")
                 for cl in cs]
        return space_time_cube(view, t0, t1, lines=lines, discs=discs, height=height, rev=f"enc_{key}_{gid}")
    fig = base_map(height, view, dim=0.3)
    place_labels(fig, size=12)
    for j, cl in enumerate(cs):
        fig.add_trace(hull_trace(cl.pts, "#ffffff", opacity=0.04 + 0.25 * (j + 1) / len(cs), width=0.5))
    for tm in teams:
        xs, ys, ends = [], [], []
        for _, p in win[win["team"] == tm].groupby("player"):
            xs += list(p["x"]) + [None]
            ys += list(p["y"]) + [None]
            ends.append(p.iloc[-1])
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name=L_(tm), legendgroup=tm, hoverinfo="name",
                                 line=dict(color=tcol[tm], width=3.5 if tm in colors_ else 2)))
        if ends:
            e = pd.DataFrame(ends)
            fig.add_trace(go.Scatter(x=e["x"], y=e["y"], mode="markers", legendgroup=tm, showlegend=False,
                                     marker=dict(size=10, color=tcol[tm], line=dict(width=1.5, color="white")),
                                     hovertext=e["player"].map(L_) + " · " + L_(tm) + " · " + e["t"].map(fmt_t),
                                     hoverinfo="text"))
    fig.add_annotation(x=row.cx, y=view[1] + 0.06 * (view[3] - view[1]), showarrow=False,
                       text=f"<b>{name}</b>", font=dict(color="white", size=14, shadow=TEXT_SHADOW))
    fig.update_layout(shapes=zone_shapes(zones_, row.t_end), margin=dict(l=0, r=0, t=10, b=0),
                      legend=dict(orientation="h", y=0, yanchor="top"))
    return fig


# ---------------- one gathering, in 3D or 2D ----------------
def render_encounter(gid: int, key: str, height: int = 580) -> None:
    row = gby[gid]
    cs = [res.clusters[i] for i in row.clusters]
    teams = list(row.teams)
    others_c = iter(OTHER_COLORS * 3)
    tcol = {tm: colors.get(tm) or next(others_c) for tm in teams}
    present = {m for cl in cs for m in cl.members}
    par = set(row.participators)
    left, right = st.columns([3, 2])
    with right:
        mode = st.segmented_control("Kiểu xem", ["3D", "2D"], default="3D", key=f"encm_{key}") or "3D"
        items = []
        for tm in teams:
            mem = set(pos.loc[pos["team"] == tm, "player"])
            items.append(f"<li><span style='color:{tcol[tm]}'>●</span> <b>{L(tm)}</b>: {len(mem & present)} người có mặt"
                         f" · {len(mem & par)} participator</li>")
        verdict(f"<b>{gname(gid)}</b> · phase {int(row.phase)} · {fmt_t(row.t_start)}–{fmt_t(row.t_end)} "
                f"({int(row.t_end - row.t_start + 10)} s, {int(row.lifetime)} bước) · {len(teams)} đội · "
                f"{int(row.n_participators)} participator · cụm TB {row.mean_size:.0f} người"
                f"<ul style='margin:6px 0 0'>{''.join(items)}</ul>")
    with left:
        fig = _enc_fig(folder, mid, gid, mode, tuple(focus), LB, height, key)
        st.plotly_chart(fig, width="stretch", key=f"encfig_{key}_{gid}")


TABS = ["🗺️ Di chuyển", "🎯 Gathering"]
tabs = st.tabs(TABS, key="result_tab", on_change="rerun")
ACTIVE = st.session_state.get("result_tab") or TABS[0]
tab_move, tab_gath = tabs

# ---------------- 🗺️ movement ----------------
with tab_move:
    if ACTIVE == TABS[0]:  # only the open tab does its work
        view = st.segmented_control("Xem", ["Đường đi", "Replay", "3D x–y–t"], default="Đường đi",
                                    key="move_view") or "Đường đi"
        if focus:
            st.markdown(" ".join(f'<span class="badge" style="background:{colors[tm]};color:#111">{L(tm)}</span>'
                                 for tm in focus), unsafe_allow_html=True)
        if view == "Đường đi":
            st.plotly_chart(_routes(folder, mid, tuple(focus), LB), width="stretch")
            for tm in focus:
                r = info.loc[tm]
                st.markdown(f"{dot(tm)} **{L(tm)}**: {r['route_str']} · {r['dist_km']:.1f} km · "
                            f"{r['n_gatherings']} gathering", unsafe_allow_html=True)
        elif view == "Replay":
            a, b = st.columns([2, 1])
            follow = a.selectbox("Bám theo đội", [None] + focus, key=f"follow_{mid}",
                                 format_func=lambda tm: "— toàn bản đồ —" if tm is None else L(tm))
            speed = b.radio("Tốc độ", ["Chậm", "Vừa", "Nhanh"], index=1, horizontal=True, key="speed")
            st.plotly_chart(_replay(folder, mid, tuple(focus), follow, {"Chậm": 450, "Vừa": 250, "Nhanh": 120}[speed],
                                    LB),
                            width="stretch")
        else:
            a, b, c3 = st.columns([3, 1, 1])
            t_range = a.slider("Khoảng thời gian", 0, T_END, (0, T_END), step=10, format="%d s", key=f"cube_t_{mid}")
            others = b.toggle("Đội khác", value=True, key="cube_others")
            gath = c3.toggle("Gathering", value=True, key="cube_gath")
            st.plotly_chart(_team_cube(folder, mid, tuple(focus), tuple(t_range), others, gath, LB), width="stretch")
            st.caption(f"{fmt_t(t_range[0])} → {fmt_t(t_range[1])} · trục đứng = thời gian · cột cam = gathering")

# ---------------- 🎯 gatherings ----------------
with tab_gath:
    if ACTIVE == TABS[1]:  # only the open tab does its work
        if gdf.empty:
            verdict("Không có gathering nào với tham số mặc định.", False)
        else:
            g = gdf.sort_values("t_start").reset_index(drop=True)
            star = [any(tm in focus for tm in teams) for teams in g["teams"]]
            phase_col = ["#9ecae1", "#6baed6", "#4292c6", "#2171b5", "#fdae6b", "#fd8d3c", "#e6550d", "#a63603",
                         "#7f2704"]
            names = [gname(int(i)) for i in g["id"]]
            gt = go.Figure(go.Bar(
                y=[("★ " if s else "") + n for n, s in zip(names, star, strict=True)], x=g["t_end"] - g["t_start"] + 10,
                base=g["t_start"], orientation="h", marker_color=[phase_col[min(int(p), 8)] for p in g["phase"]],
                text=[f"{len(teams)} đội · {n} par." for teams, n in zip(g["teams"], g["n_participators"], strict=True)],
                textposition="auto", cliponaxis=False, hoverinfo="text",
                hovertext=[f"{n} · {fmt_t(a)}–{fmt_t(b)} · phase {p} · {', '.join(L(tm) for tm in teams)}" for n, a, b, p, teams
                           in zip(names, g["t_start"], g["t_end"], g["phase"], g["teams"], strict=True)]))
            ticks = list(range(0, T_END + 1, 180))
            gt.update_layout(height=60 + 34 * len(g), margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="#FBF8F1",
                             xaxis=dict(tickvals=ticks, ticktext=[fmt_t(x) for x in ticks], range=[0, T_END]),
                             yaxis=dict(autorange="reversed"))
            st.plotly_chart(gt, width="stretch")
            st.caption("Màu = phase (xanh: đầu trận → cam/nâu: cuối trận) · ★ = có đội đang theo dõi.")
            best = int(np.argmax([sum(tm in focus for tm in teams) for teams in g["teams"]])) if focus else 0
            k = st.selectbox("Gathering", list(range(len(g))), index=best, key=f"enc_{mid}",
                             format_func=lambda i: f"{'★ ' if star[i] else ''}{names[i]} · {fmt_t(g.loc[i, 't_start'])}–"
                             f"{fmt_t(g.loc[i, 't_end'])} · {len(g.loc[i, 'teams'])} đội")
            render_encounter(int(g.loc[k, "id"]), "enc")
