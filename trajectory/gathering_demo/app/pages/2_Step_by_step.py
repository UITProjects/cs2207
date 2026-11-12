"""🔬 Step-by-step — quỹ đạo → cụm → crowd → gathering trên một trận (luồng của demo cũ)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # app/ (for `common`)
import common  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from common import q, verdict  # noqa: E402

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

common.page("Step-by-step", "🔬")
ctx = common.sidebar()
P = ctx["params"]
t = common.load_match(ctx["folder"], ctx["match_id"])
res = common.mine(ctx["folder"], ctx["match_id"], common.params_key(P))
pos, zones = t["positions"], t["zones"]
src = common.caption_source(ctx)

st.title("🔬 Step-by-step")
st.markdown(f"{src} trận `{ctx['match_id']}` · eps={P['eps']} m · min_pts={P['min_pts']} · m_c={P['m_c']} · "
            f"δ={P['delta']} m · k_c={P['k_c']} · k_p={P['k_p']} · m_p={P['m_p']}")
c = st.columns(4)
c[0].metric("Cụm (mọi t)", len(res.clusters))
c[1].metric("Crowd đóng", len(res.crowds))
c[2].metric("Gathering", len(res.gatherings))
c[3].metric("Người chơi", pos["player"].nunique())

tab1, tab2, tab3, tab4 = st.tabs(["① Quỹ đạo gốc", "② Cụm snapshot", "③ Crowd", "④ Gathering"])

with tab1:
    q("Mỗi chấm là một người chơi (màu = đội) ở bước Δt = 10 s, chỉ tính từ lúc <b>tiếp đất</b> đến lúc <b>bị loại</b>. "
      "Vòng <span style='color:#4aa3ff'><b>xanh</b></span> là bo hiện tại, vòng <b>trắng đứt</b> là bo kế tiếp. "
      "Bấm ▶ Play hoặc kéo thanh thời gian.")
    st.plotly_chart(animation(pos, zones), width="stretch")
    st.caption(f"{src} Số người còn sống giảm dần theo thời gian; phase tăng mỗi khi bo trắng mới xuất hiện.")

times = sorted(pos["t"].unique())
by_t: dict[int, list] = {}
for cl in res.clusters:
    by_t.setdefault(cl.t, []).append(cl)

with tab2:
    q("Tại một mốc t, <b>DBSCAN</b>(eps, min_pts) gom người chơi đứng gần nhau thành <b>cụm</b>. "
      "Điểm xám là nhiễu (không thuộc cụm nào). Chỉ cụm có ≥ m_c người mới có thể thành Crowd.")
    busiest = max(times, key=lambda x: sum(c.size >= P["m_c"] for c in by_t.get(x, [])), default=times[0])
    tt = st.select_slider("Mốc thời gian t", options=times, value=busiest, format_func=fmt_t, key="t_snap")
    lab = res.labels[res.labels["t"] == tt]
    cls = by_t.get(tt, [])
    zoom = st.checkbox("Phóng to vào các cụm ≥ m_c", value=False)
    big = [c for c in cls if c.size >= P["m_c"]]
    view = None
    if zoom and big:
        allp = np.vstack([c.pts for c in big])
        lo, hi = allp.min(0), allp.max(0)
        view = zoom_box(*(lo + hi) / 2, max(hi - lo) / 2 + 100, pad=1.2)
    fig = base_map(660, view)
    noise = lab[lab["cluster"] < 0]
    fig.add_trace(go.Scatter(x=noise["x"], y=noise["y"], mode="markers", name="nhiễu",
                             marker=dict(size=6, color=NOISE), text=noise["player"], hoverinfo="text"))
    for i, cl in enumerate(cls):
        col = CLUSTER_COLORS[i % len(CLUSTER_COLORS)]
        strong = cl.size >= P["m_c"]
        fig.add_trace(hull_trace(cl.pts, col, f"c{cl.k} ({cl.size})", opacity=0.35 if strong else 0.15))
        fig.add_trace(go.Scatter(x=cl.pts[:, 0], y=cl.pts[:, 1], mode="markers", name=f"c{cl.k} · {cl.size} người",
                                 marker=dict(size=8, color=col, line=dict(width=1, color="black")),
                                 text=list(cl.members), hoverinfo="text"))
        cx, cy = cl.centroid
        fig.add_annotation(x=cx, y=cy, text=f"<b>{cl.size}</b>", showarrow=False, yshift=-18,
                           font=dict(color="white" if strong else "#ddd", size=13 if strong else 10))
    fig.update_layout(shapes=zone_shapes(zones, tt), title=f"t = {fmt_t(tt)} · {len(cls)} cụm, {len(big)} cụm ≥ m_c")
    st.plotly_chart(fig, width="stretch")
    st.caption(f"{src} Nhãn trắng = số người trong cụm (đậm khi ≥ m_c = {P['m_c']}).")

link_d = {(lk.a, lk.b): lk.dH for lk in res.links}
cdf = res.crowd_df.copy()
gset = {tuple(g) for g, _, _ in res.gatherings}
gcrowds = {ci for _, _, ci in res.gatherings}

with tab3:
    q("<b>Crowd</b> = chuỗi cụm ở các mốc liên tiếp, mỗi cụm ≥ m_c người, hai cụm kề nhau có khoảng cách "
      "<b>Hausdorff</b> ≤ δ, kéo dài ≥ k_c bước. Chọn một crowd để xem các vỏ lồi theo thời gian (càng về sau càng đậm) "
      "và đường đi của tâm.")
    if cdf.empty:
        verdict("Không có crowd nào với tham số hiện tại — thử giảm m_c hoặc k_c, tăng eps/δ.", False)
    else:
        view_df = pd.DataFrame({
            "crowd": [f"Cr{i + 1}" for i in cdf["id"]], "bắt đầu": cdf["t_start"].map(fmt_t),
            "kết thúc": cdf["t_end"].map(fmt_t), "số bước": cdf["lifetime"],
            "cỡ TB": cdf["mean_size"].round(1), "phase": cdf["phase"], "địa điểm": cdf["place"],
            "→ Gathering?": ["✓" if i in gcrowds else "✗" for i in cdf["id"]]})
        st.dataframe(view_df, hide_index=True, width="stretch", height=min(38 * len(cdf) + 40, 300))
        ci = st.selectbox("Chọn crowd", list(cdf["id"]), format_func=lambda i: f"Cr{i + 1} · {cdf.loc[i, 'place']} · "
                          f"{fmt_t(cdf.loc[i, 't_start'])}–{fmt_t(cdf.loc[i, 't_end'])}", key="crowd_sel")
        seq = res.crowds[ci]
        cs = [res.clusters[i] for i in seq]
        allp = np.vstack([c.pts for c in cs])
        lo, hi = allp.min(0), allp.max(0)
        a, b = st.columns([3, 2])
        with a:
            fig = base_map(600, zoom_box(*(lo + hi) / 2, max(hi - lo) / 2 + 80, pad=1.15))
            for j, cl in enumerate(cs):
                op = 0.06 + 0.5 * (j + 1) / len(cs)
                fig.add_trace(hull_trace(cl.pts, "#ff924c", f"{fmt_t(cl.t)} · {cl.size} người", opacity=op))
            cen = np.array([c.centroid for c in cs])
            fig.add_trace(go.Scatter(x=cen[:, 0], y=cen[:, 1], mode="lines+markers", name="đường đi của tâm",
                                     line=dict(color="white", width=2), marker=dict(size=5, color="white")))
            last = cs[-1]
            fig.add_trace(go.Scatter(x=last.pts[:, 0], y=last.pts[:, 1], mode="markers", name="cụm cuối",
                                     marker=dict(size=8, color="#ffca3a", line=dict(width=1, color="black")),
                                     text=list(last.members), hoverinfo="text"))
            fig.update_layout(title=f"Cr{ci + 1}: {len(cs)} cụm liên tiếp", shapes=zone_shapes(zones, cs[-1].t))
            st.plotly_chart(fig, width="stretch")
        with b:
            d = [link_d.get((cs[j].id, cs[j + 1].id)) for j in range(len(cs) - 1)]
            hf = go.Figure(go.Bar(x=[fmt_t(cs[j + 1].t) for j in range(len(d))], y=d, marker_color="#1982c4",
                                  name="d_H(c_i, c_i+1)"))
            hf.add_hline(y=P["delta"], line_dash="dash", line_color="#B8541C", annotation_text=f"δ = {P['delta']} m")
            hf.update_layout(height=280, title="Hausdorff giữa hai cụm liên tiếp", yaxis_title="m",
                             margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(hf, width="stretch")
            sz = go.Figure(go.Bar(x=[fmt_t(c.t) for c in cs], y=[c.size for c in cs], marker_color="#ff924c"))
            sz.add_hline(y=P["m_c"], line_dash="dash", line_color="#B8541C", annotation_text=f"m_c = {P['m_c']}")
            sz.update_layout(height=250, title="Cỡ cụm theo thời gian", margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(sz, width="stretch")
            verdict(f"Mọi d<sub>H</sub> ≤ δ và mọi cụm ≥ m_c; {len(cs)} bước ≥ k_c = {P['k_c']} → là crowd. "
                    f"Không thể kéo dài thêm ở hai đầu → <b>crowd đóng</b>.", True)

with tab4:
    q("<b>Test-and-Divide</b>: participator = người có mặt ở ≥ k_p cụm của crowd. Crowd là <b>Gathering</b> nếu "
      "<b>mọi</b> cụm có ≥ m_p participator; nếu không, cắt bỏ cụm vi phạm, tính lại participator trên từng đoạn còn lại "
      "(đoạn ≥ k_c bước) và lặp lại.")
    gdf = res.gathering_df
    if cdf.empty:
        verdict("Chưa có crowd nên chưa có gathering.", False)
    else:
        ci2 = st.selectbox("Crowd để chạy TAD", list(cdf["id"]), key="tad_sel",
                           format_func=lambda i: f"Cr{i + 1} · {cdf.loc[i, 'place']} · "
                           f"{'✓ gathering' if i in gcrowds else '✗ không'}")
        td = res.tads[ci2]
        seq = res.crowds[ci2]
        lines = []
        for step in td["trace"]:
            span = np.where(step["mask"])[0]
            rng_s = f"bước {span[0] + 1}–{span[-1] + 1}"
            if step["kind"] == "test":
                if step["bad"]:
                    lines.append(f"<li><b>Test</b> {rng_s}: {len(step['par'])} participator; "
                                 f"{len(step['bad'])} cụm có &lt; m_p = {P['m_p']} → ✗</li>")
                else:
                    lines.append(f"<li><b>Test</b> {rng_s}: {len(step['par'])} participator, mọi cụm ≥ m_p → "
                                 f"<b>Gathering</b> ✓</li>")
            else:
                parts = ", ".join(f"{p['tau']} bước{'' if p['ok'] else ' (&lt; k_c, bỏ)'}" for p in step["parts"])
                lines.append(f"<li><b>Divide</b>: cắt tại {len(step['bad'])} cụm vi phạm → các đoạn: {parts or '∅'}</li>")
        verdict("<b>Vết TAD</b><ul style='margin:4px 0 0'>" + "".join(lines) + "</ul>", bool(td["gatherings"]))
        first = td["trace"][0]
        counts = [max(x, 0) for x in first["counts"]]
        cols_ = ["#8ac926" if x >= P["m_p"] else "#ff595e" for x in counts]
        bf = go.Figure(go.Bar(x=[fmt_t(res.clusters[i].t) for i in seq], y=counts, marker_color=cols_,
                              name="participator"))
        bf.add_trace(go.Bar(x=[fmt_t(res.clusters[i].t) for i in seq],
                            y=[res.clusters[i].size - c for i, c in zip(seq, counts, strict=True)],
                            marker_color="#ccc", name="không phải participator"))
        bf.add_hline(y=P["m_p"], line_dash="dash", line_color="#B8541C", annotation_text=f"m_p = {P['m_p']}")
        bf.update_layout(barmode="stack", height=280, margin=dict(l=10, r=10, t=40, b=10),
                         title="Participator trong mỗi cụm của crowd (lần Test đầu)")
        st.plotly_chart(bf, width="stretch")

        mine_g = [(k, g, par) for k, (g, par, cidx) in enumerate(res.gatherings) if cidx == ci2]
        if not mine_g:
            verdict("Crowd này <b>không</b> chứa gathering nào: người trong đám đông thay đổi liên tục "
                    "(đi ngang qua) hoặc đoạn còn lại quá ngắn.", False)
        else:
            k, g, par = mine_g[0] if len(mine_g) == 1 else mine_g[st.selectbox(
                "Gathering", list(range(len(mine_g))), format_func=lambda j: f"G{mine_g[j][0] + 1}")]
            row = gdf.loc[k]
            st.markdown(f"**G{k + 1}** · {row['place']} · {fmt_t(row['t_start'])}–{fmt_t(row['t_end'])} · "
                        f"{len(par)} participator · đội: {', '.join(row['teams'])}")
            cs = [res.clusters[i] for i in g]
            allp = np.vstack([c.pts for c in cs])
            lo, hi = allp.min(0), allp.max(0)
            view = zoom_box(*(lo + hi) / 2, max(hi - lo) / 2 + 150, pad=1.2)
            win = pos[(pos["t"] >= row["t_start"] - 60) & (pos["t"] <= row["t_end"] + 60)
                      & pos["x"].between(view[0], view[2]) & pos["y"].between(view[1], view[3])]
            st.caption("Hình động: từ 60 s trước khi hình thành đến 60 s sau khi tan. Viền đen dày = participator.")
            st.plotly_chart(animation(win, zones, highlight=set(par), view=view, height=600, frame_ms=350),
                            width="stretch")
