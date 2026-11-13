"""📦 Data Explorer — bảng trận, Δt thực tế, quỹ đạo một trận."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # app/ (for `common`)
import common  # noqa: E402
import streamlit as st  # noqa: E402
from common import q  # noqa: E402

from src.viz.map_plot import trajectories  # noqa: E402

common.page("Data Explorer", "📦")
ctx = common.sidebar(params=False)
mt = ctx["matches"]
st.title("📦 Data Explorer")
q("Mỗi dòng là một trận Erangel squad đã qua <b>crawl → parse → clean</b>. "
  "<b>Δt</b> là khoảng thời gian thật giữa hai bản ghi vị trí liên tiếp của cùng một người (trước khi resample về 10 s).")

cols = ["match_id", "mapName", "gameMode", "matchType", "createdAt", "n_players", "n_teams", "duration",
        "n_raw_points", "n_points", "raw_dt_median", "raw_dt_p10", "raw_dt_p90", "n_phases"]
show = mt[[c for c in cols if c in mt]].rename(columns={
    "n_raw_points": "điểm gốc", "n_points": "điểm sau xử lý", "raw_dt_median": "Δt median (s)",
    "raw_dt_p10": "Δt p10", "raw_dt_p90": "Δt p90", "n_phases": "số phase"})
st.dataframe(show, width="stretch", hide_index=True, height=260)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Số trận", len(mt))
if "raw_dt_median" in mt:
    c2.metric("Δt median (mọi trận)", f"{mt['raw_dt_median'].median():.2f} s")
c3.metric("Điểm sau xử lý / trận", f"{mt['n_points'].mean():,.0f}")
c4.metric("Người chơi / trận", f"{mt['n_players'].mean():.0f}")

st.subheader("Quỹ đạo của trận đang chọn")
t = common.load_match(ctx["folder"], ctx["match_id"])
pos = t["positions"]
st.caption(f"{common.caption_source(ctx)} {ctx['match_id']} · {pos['player'].nunique()} người · "
           f"{pos['team'].nunique()} đội · mỗi màu là một đội; đường đứt = khoảng trống > 10 s (không nội suy).")
st.plotly_chart(trajectories(pos), width="stretch")
with st.expander("Bảng positions (đã resample, ẩn danh)"):
    st.dataframe(pos.head(500), width="stretch", hide_index=True)
with st.expander("Kết quả cuối trận (results) và các lần bị loại (kills)"):
    a, b = st.columns(2)
    a.dataframe(t["results"].sort_values("ranking"), hide_index=True, width="stretch")
    b.dataframe(t["kills"], hide_index=True, width="stretch")
