"""🗺️ Multi-match Insights — điểm nóng theo phase, chokepoint, gathering ↔ bị loại."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # app/ (for `common`)
import common  # noqa: E402
import numpy as np  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from common import q, verdict  # noqa: E402

from src.analytics.hotspots import grid_counts, top_places  # noqa: E402
from src.analytics.outcomes import rate_table  # noqa: E402
from src.viz.map_plot import base_map  # noqa: E402

common.page("Insights", "🗺️")
ctx = common.sidebar(match_picker=False)
src = common.caption_source(ctx)
st.title("🗺️ Insights nhiều trận")
use_sb = st.toggle("Dùng tham số ở thanh bên (tính lại toàn bộ — vài chục giây)", value=False)
agg, params = common.aggregates(ctx, use_sb)
G, E, T, K = agg["gatherings"], agg["exposure"], agg["teams"], agg["kills"]
n_matches = len(agg["matches"])
q(f"Tổng hợp <b>{n_matches} trận</b>, <b>{len(G)} gathering</b> với tham số "
  f"{'ở thanh bên' if use_sb else 'mặc định'} (eps={params['eps']}, m_c={params['m_c']}, δ={params['delta']}, "
  f"k_c={params['k_c']}, k_p={params['k_p']}, m_p={params['m_p']}). "
  "Mọi con số đều kèm cỡ mẫu <b>n</b>; đây là <b>tương quan</b>, không phải nhân quả.")
if G.empty:
    verdict("Không có gathering nào với tham số này.", False)
    st.stop()

phases = sorted(G["phase"].unique())
c1, c2 = st.columns([3, 2])
with c1:
    st.subheader("Bản đồ nhiệt gathering")
    ph = st.selectbox("Phase", ["Tất cả"] + [int(p) for p in phases],
                      format_func=lambda p: p if p == "Tất cả" else f"Phase {p}")
    g = G if ph == "Tất cả" else G[G["phase"] == ph]
    gc = grid_counts(g)
    if ph == "Tất cả":
        gc = gc.groupby(["gx", "gy", "x", "y"], as_index=False).agg(count=("count", "sum"), matches=("matches", "sum"))
    fig = base_map(620)
    fig.add_trace(go.Scatter(x=gc["x"], y=gc["y"], mode="markers", name="ô 200 m",
                             marker=dict(size=8 + 5 * np.sqrt(gc["count"]), color=gc["count"], colorscale="YlOrRd",
                                         opacity=0.85, line=dict(width=0.5, color="black"), showscale=True,
                                         colorbar=dict(title="số GA", thickness=12)),
                             text=[f"{c} gathering · {m} trận" for c, m in zip(gc["count"], gc["matches"], strict=True)],
                             hoverinfo="text"))
    st.plotly_chart(fig, width="stretch")
    st.caption(f"{src} Mỗi chấm = một ô lưới 200 m chứa tâm của gathering; to/đỏ hơn = nhiều hơn.")
with c2:
    st.subheader("Top 10 chokepoint")
    tp = top_places(G, n_matches)
    st.dataframe(tp.assign(**{"% trận": tp["pct_matches"].round(0), "hình thành sau bo (s)": tp["t_after_zone"].round(0),
                              "participator TB": tp["participators"].round(1), "bị bo ép (%)": (100 * tp["forced"]).round(0)})
                 [["place", "phase", "gatherings", "% trận", "hình thành sau bo (s)", "participator TB", "bị bo ép (%)"]],
                 hide_index=True, width="stretch", height=390)
    st.caption("“% trận” = tỉ lệ trận có ≥ 1 gathering tại địa điểm đó trong phase đó. "
               "“Bị bo ép” = phase ≥ 6 hoặc nằm ở rìa bo trắng.")

st.subheader("Ở trong gathering có nguy hiểm hơn?")
lvl = st.radio("Đơn vị", ["player", "team"], horizontal=True,
               format_func=lambda x: "Người chơi" if x == "player" else "Đội (bị loại cả đội)")
rt = rate_table(E, lvl)
if len(rt):
    fig = go.Figure()
    for grp, col, name in (("baseline", "#9aa5b1", "Baseline (cùng trận, cùng khung giờ, không trong gathering)"),
                           ("participator", "#B8541C", "Participator của gathering")):
        fig.add_trace(go.Bar(x=[f"Phase {p}" for p in rt["phase"]], y=100 * rt[f"rate_{grp}"], name=name, marker_color=col,
                             text=[f"n={int(n)}" if n == n else "" for n in rt[f"n_{grp}"]], textposition="outside"))
    fig.update_layout(barmode="group", height=360, yaxis_title="% bị loại trong ≤ 120 s sau khi gathering tan",
                      margin=dict(l=10, r=10, t=30, b=10), legend=dict(orientation="h", y=1.12))
    st.plotly_chart(fig, width="stretch")
k = K.sum(numeric_only=True)
ki = k["kills_inside"] / max(k["pmin_inside"], 1e-9)
ko = k["kills_outside"] / max(k["pmin_outside"], 1e-9)
a, b, c = st.columns(3)
a.metric("Bị loại / người·phút trong vỏ gathering", f"{ki:.3f}", help=f"n = {int(k['kills_inside'])} lần bị loại")
b.metric("… ngoài gathering", f"{ko:.3f}", help=f"n = {int(k['kills_outside'])} lần bị loại")
c.metric("Tỉ số", f"×{ki / max(ko, 1e-9):.2f}")

st.subheader("Thứ hạng cuối theo số lần tham gia gathering")
t = T.copy()
t["số gathering"] = t["n_gatherings"].clip(upper=4).map(lambda v: "4+" if v >= 4 else str(v))
rk = t.groupby("số gathering")["ranking"].agg(["mean", "median", "size"]).reset_index()
fig = go.Figure(go.Box(x=t["số gathering"], y=t["ranking"], marker_color="#1982c4", boxmean=True))
fig.update_layout(height=320, yaxis_title="thứ hạng (1 = thắng)", yaxis_autorange="reversed",
                  xaxis_title="số gathering đội đã tham gia trong trận", margin=dict(l=10, r=10, t=10, b=10))
st.plotly_chart(fig, width="stretch")
st.caption("n mỗi nhóm: " + ", ".join(f"{r['số gathering']}: {r['size']}" for _, r in rk.iterrows()) +
           ". Lưu ý thiên lệch sống sót: đội sống lâu hơn có nhiều cơ hội tham gia gathering hơn.")

st.subheader("Gathering do bo ép hay do chọn?")
z = G.groupby(["phase", "zone_label"]).size().reset_index(name="n")
fig = go.Figure()
for lab, col in (("no zone", "#bbb"), ("center", "#1982c4"), ("edge", "#ff924c"), ("outside", "#6a4c93")):
    s = z[z["zone_label"] == lab]
    fig.add_trace(go.Bar(x=[f"Phase {p}" for p in s["phase"]], y=s["n"], name=lab, marker_color=col))
fig.update_layout(barmode="stack", height=300, margin=dict(l=10, r=10, t=10, b=10))
st.plotly_chart(fig, width="stretch")
st.caption(f"{src} center: tâm gathering trong 50% bán kính bo trắng · edge: 50–110% (bị bo ép) · outside: ngoài bo "
           "(chokepoint/camp, chủ động) · no zone: trước khi có bo.")
