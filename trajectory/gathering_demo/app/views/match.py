"""🎮 Trận đấu — một trận: các đội di chuyển thế nào (đường đi, replay, 3D x–y–t, xoay bo, chạm trán)."""
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

from src.analytics.movement import MAX_FOCUS, default_focus, team_summary, team_tracks, zone_gap  # noqa: E402
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

common.page("Trận đấu", "🎮")
ctx = common.sidebar(params=False)
P = default_params()
folder, mid = ctx["folder"], ctx["match_id"]
t = common.load_match(folder, mid)
res = common.mine(folder, mid, common.params_key(P))
pos, zones, kills = t["positions"], t["zones"], t["kills"]
gdf = res.gathering_df
T_END = int(pos["t"].max())


@st.cache_data(show_spinner=False, max_entries=8)
def _summary(folder: str, mid: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    tb = common.load_match(folder, mid)
    r = common.mine(folder, mid, common.params_key(default_params()))
    tr = team_tracks(tb["positions"])
    tr["gap"] = zone_gap(tr, tb["zones"])
    return team_summary(tb, r.gathering_df), tr


@st.cache_data(show_spinner="Đang dựng replay…", max_entries=12)
def _replay(folder: str, mid: str, focus: tuple, follow: str | None, frame_ms: int) -> go.Figure:
    tb = common.load_match(folder, mid)
    colors = dict(zip(focus, FOCUS_COLORS, strict=False))
    return replay(tb["positions"], tb["zones"], tb["kills"], list(focus), colors, follow=follow, frame_ms=frame_ms)


@st.cache_data(show_spinner="Đang dựng hình 3D…", max_entries=16)
def _team_cube(folder: str, mid: str, focus: tuple, t_range: tuple, others: bool, gath: bool) -> go.Figure:
    summary, tracks = _summary(folder, mid)
    r = common.mine(folder, mid, common.params_key(default_params()))
    colors = dict(zip(focus, FOCUS_COLORS, strict=False))
    return team_cube(tracks, summary, list(focus), colors, r.gathering_df, r.clusters, t_range, others, gath)


summary, tracks = _summary(folder, mid)
info = summary.set_index("team")
label = {r.team: f"{r.team} · hạng {r.rank}" for r in summary.itertuples()}

# ---------------- header ----------------
st.title("🎮 Các đội di chuyển thế nào?")
c = st.columns(4)
c[0].metric("Đội", summary["team"].nunique())
c[1].metric("Người chơi", pos["player"].nunique())
c[2].metric("Thời lượng", fmt_t(T_END))
c[3].metric("Chạm trán (gathering)", len(gdf))

default = [tm for tm in default_focus(summary) if tm in label]
focus = st.multiselect("Đội theo dõi (tối đa 4)", list(summary["team"]), default=default, max_selections=MAX_FOCUS,
                       format_func=lambda tm: label[tm], key=f"focus_{mid}")
colors = dict(zip(focus, FOCUS_COLORS, strict=False))
if focus:
    st.markdown(" ".join(f'<span class="badge" style="background:{colors[tm]};color:#111">{label[tm]}</span>'
                         for tm in focus), unsafe_allow_html=True)


def dot(tm: str) -> str:
    return f'<span style="color:{colors.get(tm, "#888")};font-size:18px">●</span>'


# ---------------- ① routes ----------------
st.header("① Đường đi")
st.plotly_chart(team_routes(tracks, summary, focus, colors, zones), width="stretch")
for tm in focus:
    r = info.loc[tm]
    end = "còn sống" if r["survived"] else f"loại {fmt_t(r['out_t'])} · {r['out_place']}"
    st.markdown(f"{dot(tm)} **{tm}** (hạng {r['rank']}): {r['route_str']} · {end} · {r['dist_km']:.1f} km",
                unsafe_allow_html=True)

# ---------------- ② replay ----------------
st.header("② Replay")
a, b = st.columns([2, 1])
follow = a.selectbox("Bám theo đội", [None] + focus, format_func=lambda tm: "— toàn bản đồ —" if tm is None
                     else label[tm], key=f"follow_{mid}")
speed = b.radio("Tốc độ", ["Chậm", "Vừa", "Nhanh"], index=1, horizontal=True, key="speed")
frame_ms = {"Chậm": 450, "Vừa": 250, "Nhanh": 120}[speed]
st.plotly_chart(_replay(folder, mid, tuple(focus), follow, frame_ms), width="stretch")

# ---------------- ③ 3D ----------------
st.header("③ Không gian – thời gian (x, y, t)")
a, b, c3 = st.columns([3, 1, 1])
t_range = a.slider("Khoảng thời gian", 0, T_END, (0, T_END), step=10, format="%d s", key=f"cube_t_{mid}")
others = b.toggle("Đội khác", value=True, key="cube_others")
gath = c3.toggle("Chạm trán", value=True, key="cube_gath")
st.plotly_chart(_team_cube(folder, mid, tuple(focus), tuple(t_range), others, gath), width="stretch")
st.caption(f"{fmt_t(t_range[0])} → {fmt_t(t_range[1])} · trục đứng = thời gian · cột cam = gathering · "
           "kéo để xoay, cuộn để phóng to")

# ---------------- ④ rotation ----------------
st.header("④ Xoay bo")
order = focus + [tm for tm in summary["team"] if tm not in focus]
tab = summary.set_index("team").loc[order].reset_index()
show = pd.DataFrame({
    "Đội": tab["team"], "Hạng": tab["rank"], "Lộ trình (đầu mỗi phase)": tab["route_str"],
    "Kết cục": [("còn sống" if s else f"loại {fmt_t(o)} · {p}")
                for s, o, p in zip(tab["survived"], tab["out_t"], tab["out_place"], strict=True)],
    "km": tab["dist_km"].round(1), "Chạm trán": tab["n_gatherings"], "Ngoài bo (s)": tab["outside_s"].astype(int)})


def _hl(row):
    col = colors.get(row["Đội"])
    return [f"background-color: {col}33" if col else ""] * len(row)


st.dataframe(show.style.apply(_hl, axis=1), hide_index=True, width="stretch", height=300)

if focus:
    zf = go.Figure()
    t_first = float(zones.loc[zones["phase"] >= 1, "t"].min()) if (zones["phase"] >= 1).any() else 0
    for tm in focus:
        tr = tracks[(tracks["team"] == tm) & (tracks["t"] >= t_first)]
        zf.add_trace(go.Scatter(x=tr["t"], y=tr["gap"].clip(-2500, 1500), mode="lines", name=label[tm],
                                line=dict(color=colors[tm], width=3), hoverinfo="text",
                                hovertext=[f"{tm} · {fmt_t(x)} · {g:+.0f} m"
                                           for x, g in zip(tr["t"], tr["gap"], strict=True)]))
    zf.add_hrect(y0=0, y1=1500, fillcolor="#ff3b30", opacity=0.08, line_width=0)
    zf.add_hline(y=0, line_color="#B8541C", line_dash="dash", annotation_text="mép bo",
                 annotation_position="bottom left")
    for ph, tt in zones.groupby("phase")["t"].min().items():
        if ph >= 1:
            zf.add_vline(x=tt, line_color="#bbb", line_width=1, annotation_text=f"P{ph}",
                         annotation_position="top", annotation_font_size=10)
    ticks = list(range(0, T_END + 1, 180))
    zf.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10), yaxis_title="m tới mép bo (> 0: ngoài bo)",
                     xaxis=dict(tickvals=ticks, ticktext=[fmt_t(x) for x in ticks], title=None),
                     legend=dict(orientation="h", y=1.15), plot_bgcolor="#FBF8F1")
    st.plotly_chart(zf, width="stretch")

# ---------------- ⑤ encounters ----------------
st.header("⑤ Chạm trán")
if gdf.empty:
    verdict("Không có gathering nào.", False)
else:
    g = gdf.sort_values("t_start").reset_index(drop=True)
    names = [f"G{i + 1} · {p}" for i, p in zip(g["id"], g["place"], strict=True)]
    star = [any(tm in focus for tm in teams) for teams in g["teams"]]
    phase_col = ["#9ecae1", "#6baed6", "#4292c6", "#2171b5", "#fdae6b", "#fd8d3c", "#e6550d", "#a63603", "#7f2704"]
    gt = go.Figure(go.Bar(
        y=[("★ " if s else "") + n for n, s in zip(names, star, strict=True)], x=g["t_end"] - g["t_start"] + 10,
        base=g["t_start"], orientation="h", marker_color=[phase_col[min(int(p), 8)] for p in g["phase"]],
        text=[f"{len(teams)} đội" for teams in g["teams"]], textposition="inside", hoverinfo="text",
        hovertext=[f"{n} · {fmt_t(a)}–{fmt_t(b)} · phase {p} · {', '.join(teams)}"
                   for n, a, b, p, teams in zip(names, g["t_start"], g["t_end"], g["phase"], g["teams"], strict=True)]))
    ticks = list(range(0, T_END + 1, 180))
    gt.update_layout(height=60 + 34 * len(g), margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="#FBF8F1",
                     xaxis=dict(tickvals=ticks, ticktext=[fmt_t(x) for x in ticks], range=[0, T_END]),
                     yaxis=dict(autorange="reversed"))
    st.plotly_chart(gt, width="stretch")

    best = int(np.argmax([sum(tm in focus for tm in teams) for teams in g["teams"]])) if focus else 0
    a, b = st.columns([3, 1])
    k = a.selectbox("Chạm trán", list(range(len(g))), index=best, key=f"enc_{mid}",
                    format_func=lambda i: f"{'★ ' if star[i] else ''}{names[i]} · {fmt_t(g.loc[i, 't_start'])}–"
                    f"{fmt_t(g.loc[i, 't_end'])} · {len(g.loc[i, 'teams'])} đội")
    mode = b.segmented_control("Kiểu xem", ["3D", "2D"], default="3D", key="enc_mode") or "3D"
    row = g.loc[k]
    cs = [res.clusters[i] for i in row["clusters"]]
    allp = np.vstack([cl.pts for cl in cs])
    lo, hi = allp.min(0), allp.max(0)
    view = zoom_box(*(lo + hi) / 2, max(hi - lo) / 2 + 250, pad=1.2, min_half=450)
    t0, t1 = row["t_start"] - 60, row["t_end"] + 60
    teams = list(row["teams"])
    others_c = iter(OTHER_COLORS * 3)
    tcol = {tm: colors.get(tm) or next(others_c) for tm in teams}
    win = pos[pos["team"].isin(teams) & pos["t"].between(t0, t1)].sort_values(["player", "t"])
    kw = kills[kills["t"].between(t0, t1 + 60) & kills["x"].between(view[0], view[2])
               & kills["y"].between(view[1], view[3])]

    left, right = st.columns([3, 2])
    with left:
        if mode == "3D":
            lines = [dict(df=win[win["team"] == tm], color=tcol[tm], width=7 if tm in colors else 3, name=label[tm],
                          legend=True, markers=False) for tm in teams]
            discs = [dict(pts=cl.pts, t=cl.t, color=ORANGE, opacity=0.35, hover=f"{fmt_t(cl.t)} · {cl.size} người")
                     for cl in cs]
            pts = [dict(x=r_.x, y=r_.y, t=r_.t, color="#ff2d55", symbol="x", size=5,
                        hover=f"✖ {r_.victim} ({r_.victim_team}) · {fmt_t(r_.t)}") for r_ in kw.itertuples()]
            fig = space_time_cube(view, t0, t1 + 60, lines=lines, discs=discs, points=pts, height=620,
                                  rev=f"enc_{mid}_{k}")
        else:
            fig = base_map(620, view, dim=0.3)
            place_labels(fig, size=12)
            for j, cl in enumerate(cs):
                fig.add_trace(hull_trace(cl.pts, "#ffffff", opacity=0.04 + 0.25 * (j + 1) / len(cs), width=0.5))
            for tm in teams:
                xs, ys, ends = [], [], []
                for _, p in win[win["team"] == tm].groupby("player"):
                    xs += list(p["x"]) + [None]
                    ys += list(p["y"]) + [None]
                    ends.append(p.iloc[-1])
                fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name=label[tm], legendgroup=tm, hoverinfo="name",
                                         line=dict(color=tcol[tm], width=3.5 if tm in colors else 2)))
                if ends:
                    e = pd.DataFrame(ends)
                    fig.add_trace(go.Scatter(x=e["x"], y=e["y"], mode="markers", legendgroup=tm, showlegend=False,
                                             marker=dict(size=10, color=tcol[tm], line=dict(width=1.5, color="white")),
                                             hovertext=e["player"] + " · " + tm + " · " + e["t"].map(fmt_t),
                                             hoverinfo="text"))
            fig.add_trace(go.Scatter(x=kw["x"], y=kw["y"], mode="markers", name="bị loại", hoverinfo="text",
                                     marker=dict(size=14, symbol="x", color="#ff2d55", line=dict(width=1, color="white")),
                                     hovertext=[f"✖ {v} ({vt}) · {fmt_t(tt)}" for v, vt, tt in
                                                zip(kw["victim"], kw["victim_team"], kw["t"], strict=True)]))
            fig.add_annotation(x=row["cx"], y=view[1] + 0.06 * (view[3] - view[1]), showarrow=False,
                               text=f"<b>{names[k]}</b> · {fmt_t(row['t_start'])}–{fmt_t(row['t_end'])}",
                               font=dict(color="white", size=14, shadow=TEXT_SHADOW))
            fig.update_layout(shapes=zone_shapes(zones, row["t_end"]), margin=dict(l=0, r=0, t=10, b=0),
                              legend=dict(orientation="h", y=0, yanchor="top"))
        st.plotly_chart(fig, width="stretch")
    with right:
        death = kills.groupby("victim")["t"].min()
        present = {m for cl in cs for m in cl.members}
        lines_html, hurt = [], 0
        for tm in sorted(teams, key=lambda x: info.loc[x, "rank"]):
            mem = sorted(pos.loc[pos["team"] == tm, "player"].unique())
            here = [m for m in mem if m in present]
            lost = [m for m in mem if row["t_start"] <= death.get(m, np.inf) <= row["t_end"] + 120]
            alive_after = [m for m in mem if death.get(m, np.inf) > row["t_end"] + 120]
            hurt += bool(lost)
            out = ("<b>bị loại cả đội</b>" if not alive_after else
                   f"mất {len(lost)} ({', '.join(fmt_t(death[m]) for m in lost)})" if lost else "an toàn")
            lines_html.append(f"<li><span style='color:{tcol[tm]}'>●</span> <b>{tm}</b> (hạng {info.loc[tm, 'rank']}): "
                              f"{len(here)} người → {out}</li>")
        verdict(f"<b>{names[k]}</b> · phase {int(row['phase'])} · {int(row['t_end'] - row['t_start'] + 10)} s · "
                f"{len(teams)} đội · {int(row['n_participators'])} participator"
                f"<ul style='margin:6px 0 0'>{''.join(lines_html)}</ul>"
                f"Trong lúc + 2 phút sau: <b>{hurt}/{len(teams)} đội mất người</b>", hurt == 0)
        st.page_link("views/algorithm.py", label="Thuật toán trên trận này →", icon="🔬")
