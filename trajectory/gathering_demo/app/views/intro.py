"""🏠 Giới thiệu — vấn đề, định nghĩa, pipeline, nguồn dữ liệu, giới hạn."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # app/ (for `common`)
import common  # noqa: E402
import numpy as np  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from common import q, verdict  # noqa: E402

common.page("Gathering · PUBG", "🎯")
ctx = common.sidebar(match_picker=False, params=False)
mt = ctx["matches"]

st.markdown('<div class="kicker">CS2207 · KHAI PHÁ DỮ LIỆU QUỸ ĐẠO · NHÓM 12</div>', unsafe_allow_html=True)
st.title("Gathering Pattern trên quỹ đạo PUBG")
q("<b>Bài toán của nhà phân tích giải đấu:</b> giả sử đây là một trận đấu giải — 25 đội × 4 người trên Erangel. "
  "Ban huấn luyện muốn biết: các đội <b>nhảy ở đâu</b>, <b>xoay bo</b> theo tuyến nào và lúc nào, "
  "và <b>chạm trán nhau ở đâu</b> (hot drop, cầu sang đảo Quân sự, vòng bo cuối). Xem lại VOD bằng mắt rất tốn công; "
  "ta <b>khai phá tự động</b> từ quỹ đạo: tìm những nơi nhiều đội dồn lại thành đám đông kéo dài — "
  "<b>Gathering pattern</b>.")

c1, c2, c3 = st.columns(3)
c1.metric("Số trận", len(mt))
c2.metric("Nguồn", common.SOURCE_LABEL.get(ctx["source"], ctx["source"]))
if len(mt):
    c3.metric("Khoảng thời gian", f"{str(mt['createdAt'].min())[:10]} → {str(mt['createdAt'].max())[:10]}")

st.header("1 · Bốn khái niệm (Zheng et al., ICDE 2013)")


def illus() -> go.Figure:
    rng = np.random.default_rng(3)
    fig = go.Figure()
    core = rng.normal(0, 0.35, (7, 2))
    for s in range(4):
        ox = s * 3.2
        pts = core + rng.normal(0, 0.12, core.shape) + [ox, 0.15 * s]
        vis = rng.normal(0, 0.4, (2, 2)) + [ox, 0.15 * s]
        allp = np.vstack([pts, vis])
        from scipy.spatial import ConvexHull

        h = ConvexHull(allp)
        v = allp[h.vertices]
        fig.add_trace(go.Scatter(x=list(v[:, 0]) + [v[0, 0]], y=list(v[:, 1]) + [v[0, 1]], fill="toself",
                                 mode="lines", line=dict(color="#B8541C"), opacity=0.25, showlegend=False,
                                 hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=pts[:, 0], y=pts[:, 1], mode="markers", showlegend=s == 0, name="Participator",
                                 marker=dict(size=10, color="#1982c4", line=dict(width=2, color="black"))))
        fig.add_trace(go.Scatter(x=vis[:, 0], y=vis[:, 1], mode="markers", showlegend=s == 0,
                                 name="Người qua đường", marker=dict(size=9, color="#bbb")))
        fig.add_annotation(x=ox, y=1.25, text=f"c<sub>t{s + 1}</sub>", showarrow=False)
        if s < 3:
            fig.add_annotation(x=ox + 1.6, y=0.2, text="d<sub>H</sub> ≤ δ", showarrow=False, font=dict(color="#B8541C"))
    fig.update_layout(height=230, margin=dict(l=0, r=0, t=10, b=0), xaxis_visible=False, yaxis_visible=False,
                      plot_bgcolor="#FBF8F1", legend=dict(orientation="h", y=-0.05))
    return fig


cols = st.columns(4)
defs = [
    ("① Cluster", "Tại mỗi mốc thời gian t (Δt = 10 s), chạy <b>DBSCAN</b>(eps, min_pts) trên vị trí người "
                 "chơi còn sống và đã tiếp đất → các cụm C<sub>t</sub>."),
    ("② Crowd", "Chuỗi cụm ở các mốc <b>liên tiếp</b>, mỗi cụm ≥ m_c người, hai cụm kề nhau có khoảng cách "
               "<b>Hausdorff</b> ≤ δ, kéo dài ≥ k_c bước. Chỉ lấy crowd <i>đóng</i>."),
    ("③ Participator", "Người xuất hiện trong ≥ k_p cụm của crowd (không cần liên tiếp) — người "
                      "<b>thật sự ở lại</b>, không phải đi ngang qua."),
    ("④ Gathering", "Crowd mà <b>mọi</b> cụm có ≥ m_p participator. Nếu không: cắt bỏ cụm vi phạm, "
                   "tính lại participator trên từng đoạn (<b>Test-and-Divide</b>)."),
]
for col, (h, txt) in zip(cols, defs, strict=True):
    col.markdown(f"**{h}**")
    col.markdown(f'<div class="q" style="font-size:14px">{txt}</div>', unsafe_allow_html=True)
st.plotly_chart(illus(), width="stretch")
st.caption("Minh hoạ: 4 cụm liên tiếp (vùng cam) tạo thành một Crowd; chấm xanh viền đen là Participator, "
           "chấm xám chỉ đi ngang qua. Crowd là Gathering khi mỗi cụm có đủ ≥ m_p chấm xanh.")

st.header("2 · Pipeline")
st.graphviz_chart("""
digraph { rankdir=LR; node [shape=box, style="rounded,filled", fillcolor="#FBF8F1", color="#B8541C", fontname="sans"];
 api [label="PUBG API\\n/samples · /matches\\ntelemetry (.json.gz)"]; mock [label="Mock simulator\\n(cùng schema)"];
 crawl [label="crawl.py\\nlọc Baltic_Main · squad\\nofficial/competitive"];
 parse [label="parse\\ncm→m · ẩn danh P001/T01"]; clean [label="clean\\ncắt tiếp đất / chết\\nresample Δt=10 s · phase"];
 mine [label="DBSCAN → Crowd (Alg.1)\\n→ TAD → Gathering"]; ana [label="Analytics\\nhotspot · outcome · zone"];
 app [label="Streamlit\\nStep-by-step · Insights\\nCoach View"];
 api -> crawl; mock -> crawl; crawl -> parse -> clean -> mine -> ana -> app; mine -> app; }
""")

st.header("3 · Cách dùng demo")
st.markdown("""
- **🎮 Phân tích trận** — một trận, tập trung vào **cách các đội di chuyển**: đường đi của từng đội, replay có vệt,
  xoay bo theo phase, và các lần chạm trán (gathering) được thuật toán tìm ra.
- **🔬 Thuật toán từng bước** — cùng trận đó, chạy thuật toán từng bước: quỹ đạo → cụm → crowd → gathering.
  Kéo tham số ở thanh bên để thấy kết quả đổi theo.
""")
st.page_link("views/match.py", label="Bắt đầu: Phân tích trận →", icon="🎮")

st.header("4 · Nguồn dữ liệu & giới hạn")
if ctx["source"] == "mock":
    verdict("Đang dùng <b>MOCK DATA</b> (trận kiểu public, 25 squad — dùng như <i>ví dụ</i> cho trận giải): trận giả lập có cùng schema JSON với PUBG API (máy bay, nhảy dù, 8 vòng bo, "
            "di chuyển qua cầu, xe, loại người). Các gathering được <i>dàn dựng</i> (hot drop, chốt cầu, bo cuối) có "
            "ground truth để kiểm tra thuật toán (recall ≥ 0.8). Dữ liệu thật được thu qua PUBG API khi có key.", False)
else:
    verdict("Đang dùng <b>dữ liệu PUBG thật</b> từ <code>/shards/steam/samples</code> (Erangel, squad, official/competitive).",
            True)
st.markdown("""
- Vị trí chỉ được ghi khoảng **10 s/lần** → phù hợp hành vi vĩ mô (tụ tập, xoay bo), **không** phân tích đấu súng.
- Vòng bo ngẫu nhiên → luôn so sánh **trong cùng phase / điều kiện bo**.
- Kết quả là **tương quan, không phải nhân quả**; luôn kèm cỡ mẫu *n*.
- Dữ liệu ranked công khai ≠ giải đấu chuyên nghiệp.
- Toạ độ địa danh trong `assets/erangel_places.yaml` là ước lượng (đã hiệu chỉnh bằng mắt trên bản đồ).
""")
