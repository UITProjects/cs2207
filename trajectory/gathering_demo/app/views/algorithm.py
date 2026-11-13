"""🔬 Thuật toán — quỹ đạo → cụm → crowd → gathering trên trận này, xem 3D (x, y, t) hoặc 2D."""
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

from src.viz.cube import FULL, algo_cube, crowd_window, team_palette, window_teams  # noqa: E402
from src.viz.map_plot import (  # noqa: E402
    CLUSTER_COLORS,
    NOISE,
    animation,
    base_map,
    fmt_t,
    hull_trace,
    zone_shapes,
    zoom_box,
)

common.page("Thuật toán", "🔬")
ctx = common.sidebar()
P = ctx["params"]
folder, mid = ctx["folder"], ctx["match_id"]
t = common.load_match(folder, mid)
res = common.mine(folder, mid, common.params_key(P))
pos, zones = t["positions"], t["zones"]
times = sorted(pos["t"].unique())
MAX_FULL_STEPS = 60

st.title("🔬 Thuật toán")
c = st.columns([1, 1, 1, 2])
c[0].metric("Cụm (mọi t)", len(res.clusters))
c[1].metric("Crowd đóng", len(res.crowds))
c[2].metric("Gathering", len(res.gatherings))
with c[3]:
    VIEW_3D, VIEW_2D = "🧊 3D x–y–t", "🗺️ 2D"
    mode = st.segmented_control("Kiểu xem", [VIEW_3D, VIEW_2D], default=VIEW_3D, key="algo_view") or VIEW_3D
is3d = mode == VIEW_3D

cdf = res.crowd_df.copy()
gcrowds = {ci for _, _, ci in res.gatherings}


def crowd_label(i: int) -> str:
    return f"Cr{i + 1} · {cdf.loc[i, 'place']} · {fmt_t(cdf.loc[i, 't_start'])}–{fmt_t(cdf.loc[i, 't_end'])}"


@st.cache_data(show_spinner="Đang dựng hình 3D…", max_entries=32)
def _cube(folder: str, mid: str, pk: tuple, mode: str, view: tuple, t_lo: float, t_hi: float,
          crowd: int | None, noise: bool, connect: bool, teams: tuple, by: str, colors: tuple) -> go.Figure:
    r = common.mine(folder, mid, pk)
    return algo_cube(r, common.load_match(folder, mid)["positions"], mode, view, t_lo, t_hi, crowd, noise, connect,
                     teams=list(teams), by=by, colors=dict(colors))


def window_row(key: str) -> tuple[tuple, float, float, int | None]:
    """Area/time window for tabs ① ②: one crowd's area and span, or the whole map with a time range."""
    a, b = st.columns([2, 3])
    opts = [None] + list(cdf["id"]) if len(cdf) else [None]
    pick = a.selectbox("Vùng xem", opts, index=1 if len(opts) > 1 else 0, key=f"win_{key}",
                       format_func=lambda i: "Toàn bản đồ" if i is None else crowd_label(i))
    if pick is None:
        lo, hi = b.select_slider("Khoảng thời gian (≤ 10 phút)", options=times, key=f"rng_{key}",
                                 value=(times[0], times[min(30, len(times) - 1)]), format_func=fmt_t)
        if (hi - lo) / 10 > MAX_FULL_STEPS:
            hi = lo + 10 * MAX_FULL_STEPS
            b.caption(f"Giới hạn 10 phút: {fmt_t(lo)}–{fmt_t(hi)}")
        return FULL, lo, hi, None
    view, lo, hi = crowd_window(res, pick)
    b.caption(f"{fmt_t(lo)} → {fmt_t(hi)} · vùng {int(view[2] - view[0])} m")
    return view, lo, hi, pick


BY_TEAM, BY_PLAYER = "Đội (tâm)", "Từng người"


def team_row(key: str, view, lo: float, hi: float, noise_toggle: bool = False) -> dict:
    """Team filter + team-centre / per-player switch. Returns kwargs for _cube (teams, by, colors, noise, connect)."""
    wt = window_teams(pos, view, lo, hi)
    colors = team_palette(wt)
    a, b, c_ = st.columns([4, 2, 1.4])
    wkey = f"{key}_{int(view[0])}_{int(view[1])}_{int(lo)}_{int(hi)}"  # new window → defaults reset
    teams = a.multiselect(f"Đội ({len(wt)} đội trong vùng)", wt, default=wt, key=f"teams_{wkey}")
    by = b.segmented_control("Vẽ theo", [BY_TEAM, BY_PLAYER], default=BY_TEAM, key=f"by_{key}") or BY_TEAM
    connect, noise = True, False
    if by == BY_PLAYER:
        connect = c_.toggle("Nối quỹ đạo", value=True, key=f"conn_{key}")
        if noise_toggle:
            noise = c_.toggle("Hiện nhiễu", value=False, key=f"noise_{key}")
    if teams:
        st.markdown(" ".join(f'<span class="badge" style="background:{colors[tm]}">{tm}</span>' for tm in teams),
                    unsafe_allow_html=True)
    return dict(teams=tuple(teams), by="team" if by == BY_TEAM else "player", colors=tuple(sorted(colors.items())),
                noise=noise, connect=connect)


def cube(mode: str, view, lo, hi, crowd, key: str, noise_toggle: bool = False) -> None:
    kw = team_row(key, view, lo, hi, noise_toggle)
    st.plotly_chart(_cube(folder, mid, pk, mode, view, lo, hi, crowd, kw["noise"], kw["connect"], kw["teams"],
                          kw["by"], kw["colors"]), width="stretch")


pk = common.params_key(P)
tab1, tab2, tab3, tab4 = st.tabs(["① Quỹ đạo", "② Cụm snapshot", "③ Crowd", "④ Gathering"])
by_t: dict[int, list] = {}
for cl in res.clusters:
    by_t.setdefault(cl.t, []).append(cl)

with tab1:
    if is3d:
        view, lo, hi, cr = window_row("raw")
        cube("raw", view, lo, hi, cr, "raw")
    else:
        st.plotly_chart(animation(pos, zones), width="stretch")

with tab2:
    st.caption(f"DBSCAN eps = {P['eps']} m · min_pts = {P['min_pts']} · đĩa đậm = cụm ≥ m_c = {P['m_c']}")
    if is3d:
        view, lo, hi, cr = window_row("clusters")
        cube("clusters", view, lo, hi, cr, "clusters", noise_toggle=True)
    else:
        busiest = max(times, key=lambda x: sum(c.size >= P["m_c"] for c in by_t.get(x, [])), default=times[0])
        tt = st.select_slider("Mốc t", options=times, value=busiest, format_func=fmt_t, key="t_snap")
        lab = res.labels[res.labels["t"] == tt]
        cls = by_t.get(tt, [])
        big = [c for c in cls if c.size >= P["m_c"]]
        view = None
        if st.checkbox("Phóng to vào các cụm ≥ m_c", value=False) and big:
            allp = np.vstack([c.pts for c in big])
            lo_, hi_ = allp.min(0), allp.max(0)
            view = zoom_box(*(lo_ + hi_) / 2, max(hi_ - lo_) / 2 + 100, pad=1.2)
        fig = base_map(660, view)
        noise = lab[lab["cluster"] < 0]
        fig.add_trace(go.Scatter(x=noise["x"], y=noise["y"], mode="markers", name="nhiễu",
                                 marker=dict(size=6, color=NOISE), text=noise["player"], hoverinfo="text"))
        for i, cl in enumerate(cls):
            col = CLUSTER_COLORS[i % len(CLUSTER_COLORS)]
            strong = cl.size >= P["m_c"]
            fig.add_trace(hull_trace(cl.pts, col, f"c{cl.k} ({cl.size})", opacity=0.35 if strong else 0.15))
            fig.add_trace(go.Scatter(x=cl.pts[:, 0], y=cl.pts[:, 1], mode="markers", name=f"c{cl.k} · {cl.size}",
                                     marker=dict(size=8, color=col, line=dict(width=1, color="black")),
                                     text=list(cl.members), hoverinfo="text"))
            cx, cy = cl.centroid
            fig.add_annotation(x=cx, y=cy, text=f"<b>{cl.size}</b>", showarrow=False, yshift=-18,
                               font=dict(color="white" if strong else "#ddd", size=13 if strong else 10))
        fig.update_layout(shapes=zone_shapes(zones, tt), title=f"t = {fmt_t(tt)} · {len(cls)} cụm, {len(big)} ≥ m_c")
        st.plotly_chart(fig, width="stretch")

link_d = {(lk.a, lk.b): lk.dH for lk in res.links}

with tab3:
    st.caption(f"m_c = {P['m_c']} · δ = {P['delta']} m · k_c = {P['k_c']} bước")
    if cdf.empty:
        verdict("Không có crowd với tham số hiện tại.", False)
    else:
        view_df = pd.DataFrame({
            "crowd": [f"Cr{i + 1}" for i in cdf["id"]], "bắt đầu": cdf["t_start"].map(fmt_t),
            "kết thúc": cdf["t_end"].map(fmt_t), "bước": cdf["lifetime"], "cỡ TB": cdf["mean_size"].round(1),
            "phase": cdf["phase"], "địa điểm": cdf["place"],
            "→ Gathering?": ["✓" if i in gcrowds else "✗" for i in cdf["id"]]})
        st.dataframe(view_df, hide_index=True, width="stretch", height=min(38 * len(cdf) + 40, 260))
        ci = st.selectbox("Crowd", list(cdf["id"]), format_func=crowd_label, key="crowd_sel")
        seq = res.crowds[ci]
        cs = [res.clusters[i] for i in seq]
        a, b = st.columns([3, 2])
        with a:
            if is3d:
                view, lo, hi = crowd_window(res, ci)
                cube("crowds", view, lo, hi, ci, "crowds")
            else:
                allp = np.vstack([c.pts for c in cs])
                lo_, hi_ = allp.min(0), allp.max(0)
                fig = base_map(600, zoom_box(*(lo_ + hi_) / 2, max(hi_ - lo_) / 2 + 80, pad=1.15))
                for j, cl in enumerate(cs):
                    fig.add_trace(hull_trace(cl.pts, "#ff924c", f"{fmt_t(cl.t)} · {cl.size}",
                                             opacity=0.06 + 0.5 * (j + 1) / len(cs)))
                cen = np.array([c.centroid for c in cs])
                fig.add_trace(go.Scatter(x=cen[:, 0], y=cen[:, 1], mode="lines+markers", name="tâm",
                                         line=dict(color="white", width=2), marker=dict(size=5, color="white")))
                fig.update_layout(title=f"Cr{ci + 1}: {len(cs)} cụm liên tiếp", shapes=zone_shapes(zones, cs[-1].t))
                st.plotly_chart(fig, width="stretch")
        with b:
            d = [link_d.get((cs[j].id, cs[j + 1].id)) for j in range(len(cs) - 1)]
            hf = go.Figure(go.Bar(x=[fmt_t(cs[j + 1].t) for j in range(len(d))], y=d, marker_color="#1982c4"))
            hf.add_hline(y=P["delta"], line_dash="dash", line_color="#B8541C", annotation_text=f"δ = {P['delta']} m")
            hf.update_layout(height=280, title="d_H giữa hai cụm liên tiếp", yaxis_title="m",
                             margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(hf, width="stretch")
            sz = go.Figure(go.Bar(x=[fmt_t(c.t) for c in cs], y=[c.size for c in cs], marker_color="#ff924c"))
            sz.add_hline(y=P["m_c"], line_dash="dash", line_color="#B8541C", annotation_text=f"m_c = {P['m_c']}")
            sz.update_layout(height=250, title="Cỡ cụm", margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(sz, width="stretch")

with tab4:
    st.caption(f"k_p = {P['k_p']} · m_p = {P['m_p']} · nét đậm = có participator · nét mảnh đứt = chỉ đi qua · "
               "đĩa xanh = cụm thuộc gathering")
    gdf = res.gathering_df
    if cdf.empty:
        verdict("Chưa có crowd nên chưa có gathering.", False)
    else:
        ci2 = st.selectbox("Crowd", list(cdf["id"]), key="tad_sel",
                           format_func=lambda i: f"{crowd_label(i)} · {'✓ gathering' if i in gcrowds else '✗'}")
        td = res.tads[ci2]
        seq = res.crowds[ci2]
        a, b = st.columns([3, 2])
        with b:
            lines = []
            for step in td["trace"]:
                span = np.where(step["mask"])[0]
                rng_s = f"bước {span[0] + 1}–{span[-1] + 1}"
                if step["kind"] == "test":
                    lines.append(f"<li><b>Test</b> {rng_s}: {len(step['par'])} participator; "
                                 + (f"{len(step['bad'])} cụm &lt; m_p ✗" if step["bad"] else "<b>Gathering</b> ✓")
                                 + "</li>")
                else:
                    parts = ", ".join(f"{p['tau']} bước{'' if p['ok'] else ' (&lt; k_c)'}" for p in step["parts"])
                    lines.append(f"<li><b>Divide</b>: cắt {len(step['bad'])} cụm → {parts or '∅'}</li>")
            verdict("<b>TAD</b><ul style='margin:4px 0 0'>" + "".join(lines) + "</ul>", bool(td["gatherings"]))
            first = td["trace"][0]
            counts = [max(x, 0) for x in first["counts"]]
            bf = go.Figure(go.Bar(x=[fmt_t(res.clusters[i].t) for i in seq], y=counts, name="participator",
                                  marker_color=["#8ac926" if x >= P["m_p"] else "#ff595e" for x in counts]))
            bf.add_trace(go.Bar(x=[fmt_t(res.clusters[i].t) for i in seq],
                                y=[res.clusters[i].size - c for i, c in zip(seq, counts, strict=True)],
                                marker_color="#ccc", name="khác"))
            bf.add_hline(y=P["m_p"], line_dash="dash", line_color="#B8541C", annotation_text=f"m_p = {P['m_p']}")
            bf.update_layout(barmode="stack", height=280, margin=dict(l=10, r=10, t=40, b=10),
                             title="Participator mỗi cụm", legend=dict(orientation="h", y=-0.25))
            st.plotly_chart(bf, width="stretch")
            mine_g = [(k, g, par) for k, (g, par, cidx) in enumerate(res.gatherings) if cidx == ci2]
            for k, _, par in mine_g:
                row = gdf.loc[k]
                st.markdown(f"**G{k + 1}** · {row['place']} · {fmt_t(row['t_start'])}–{fmt_t(row['t_end'])} · "
                            f"{len(par)} participator · {', '.join(row['teams'])}")
        with a:
            if is3d:
                view, lo, hi = crowd_window(res, ci2)
                cube("participators", view, lo, hi, ci2, "par")
            elif mine_g:
                k, g, par = mine_g[0]
                row = gdf.loc[k]
                cs = [res.clusters[i] for i in g]
                allp = np.vstack([c.pts for c in cs])
                lo_, hi_ = allp.min(0), allp.max(0)
                view = zoom_box(*(lo_ + hi_) / 2, max(hi_ - lo_) / 2 + 150, pad=1.2)
                win = pos[(pos["t"] >= row["t_start"] - 60) & (pos["t"] <= row["t_end"] + 60)
                          & pos["x"].between(view[0], view[2]) & pos["y"].between(view[1], view[3])]
                st.plotly_chart(animation(win, zones, highlight=set(par), view=view, height=600, frame_ms=350),
                                width="stretch")
            else:
                verdict("Crowd này không có gathering.", False)
