"""⚙️ Sensitivity — quét một tham số, xem số crowd / gathering / participator thay đổi."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # app/ (for `common`)
import common  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from common import q  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402

common.page("Sensitivity", "⚙️")
ctx = common.sidebar()
src = common.caption_source(ctx)
P = ctx["params"]
st.title("⚙️ Sensitivity")
q("Giữ nguyên các tham số khác ở thanh bên, <b>quét một tham số</b> và chạy lại toàn bộ pipeline trên trận đang chọn "
  "(hoặc vài trận). Đường cong cho thấy kết quả nhạy với tham số nào và vùng nào ổn định.")
SWEEP = {"eps": [75, 100, 125, 150, 175, 200, 250, 300], "delta": [100, 150, 200, 250, 300, 400, 500, 700],
         "m_c": [4, 6, 8, 10, 12, 16, 20], "k_c": [3, 4, 6, 8, 10, 15, 20], "k_p": [2, 3, 4, 5, 6],
         "m_p": [3, 4, 5, 6, 7, 8], "min_pts": [2, 3, 4, 5, 6]}
a, b = st.columns([1, 1])
key = a.selectbox("Tham số", list(SWEEP), index=1, format_func=lambda k: common.PARAM_UI[k][0])
n_max = min(5, len(ctx["matches"]))
n_m = b.slider("Số trận", 1, n_max, 1, help="Trận đang chọn + các trận kế tiếp") if n_max > 1 else 1


@st.cache_data(show_spinner="Đang quét…", max_entries=16)
def sweep(folder: str, ids: tuple, key: str, base: tuple) -> pd.DataFrame:
    rows = []
    for v in SWEEP[key]:
        p = dict(base)
        p[key] = v
        p["k_p"] = min(p["k_p"], p["k_c"])
        p["m_p"] = min(p["m_p"], p["m_c"])
        for mid in ids:
            r = common.mine(folder, mid, common.params_key(p))
            g = r.gathering_df
            rows.append(dict(value=v, match=mid, crowds=len(r.crowds), gatherings=len(r.gatherings),
                             participators=float(g["n_participators"].mean()) if len(g) else np.nan,
                             lifetime=float(r.crowd_df["lifetime"].mean() * 10) if len(r.crowd_df) else np.nan))
    return pd.DataFrame(rows).groupby("value", as_index=False).mean(numeric_only=True)


ids = list(ctx["matches"]["match_id"])
i0 = ids.index(ctx["match_id"])
sel = tuple((ids[i0:] + ids[:i0])[:n_m])
df = sweep(ctx["folder"], sel, key, common.params_key(P))
fig = make_subplots(specs=[[{"secondary_y": True}]])
fig.add_trace(go.Scatter(x=df["value"], y=df["crowds"], name="# crowd", mode="lines+markers", line=dict(color="#ff924c")))
fig.add_trace(go.Scatter(x=df["value"], y=df["gatherings"], name="# gathering", mode="lines+markers",
                         line=dict(color="#B8541C", width=3)))
fig.add_trace(go.Scatter(x=df["value"], y=df["participators"], name="participator TB / gathering", mode="lines+markers",
                         line=dict(color="#1982c4", dash="dot")), secondary_y=True)
fig.add_vline(x=P[key], line_dash="dash", line_color="#888", annotation_text="giá trị hiện tại")
fig.update_layout(height=420, xaxis_title=common.PARAM_UI[key][0], margin=dict(l=10, r=10, t=30, b=10),
                  legend=dict(orientation="h", y=1.1))
fig.update_yaxes(title_text="số lượng (TB / trận)", secondary_y=False)
fig.update_yaxes(title_text="participator", secondary_y=True)
st.plotly_chart(fig, width="stretch")
st.caption(f"{src} {len(sel)} trận · các tham số khác: " + ", ".join(f"{k}={v}" for k, v in P.items() if k != key))
st.dataframe(df.round(2), hide_index=True, width="stretch")
st.subheader("Vì sao chọn tham số mặc định?")
st.markdown("""
- **eps = 150 m, min_pts = 3** — một squad tản ra trong một khu nhà ~50–100 m; 150 m nối được các squad đang đánh nhau
  trong cùng một cụm nhà mà không nối hai làng khác nhau.
- **m_c = 8** — ≥ 2 squad: một squad đi cùng nhau (4 người) **không** được tính là gathering.
- **δ = 300 m** — trong 10 s người chạy bộ đi ~60 m, xe ~150–300 m; δ = 300 m cho phép cụm trượt theo xe nhưng
  không nhảy sang chỗ khác.
- **k_c = 6 (60 s), k_p = 4, m_p = 6** — một trận giao tranh có ý nghĩa kéo dài ≥ 1 phút; participator phải ở lại
  ≥ 40 s; mỗi cụm cần ≥ 6 người "ở lại thật".
- Trên dữ liệu mock, mặc định cho **recall 0.97** so với ground truth (`scripts/validate_mock.py`), và kết quả không đổi
  khi eps/δ/m_p dịch nhẹ (margin test trong `tests/test_mining.py`).
""")
