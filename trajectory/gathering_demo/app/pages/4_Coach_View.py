"""🎯 Coach View — rủi ro tuyến/điểm theo phase và báo cáo VOD cho một đội."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # app/ (for `common`)
import common  # noqa: E402
import numpy as np  # noqa: E402
import streamlit as st  # noqa: E402
from common import q, verdict  # noqa: E402

from src.analytics.aggregate import mine_one  # noqa: E402
from src.analytics.team_report import team_report  # noqa: E402

common.page("Coach View", "🎯")
ctx = common.sidebar()
src = common.caption_source(ctx)
st.title("🎯 Coach View")
agg, params = common.aggregates(ctx, use_sidebar=False)
G, E = agg["gatherings"], agg["exposure"]
n_matches = len(agg["matches"])

tab1, tab2 = st.tabs(["Rủi ro tuyến / điểm", "Báo cáo đội (VOD)"])
with tab1:
    q("Chọn <b>phase</b> và <b>địa điểm</b> squad định đi qua → xác suất có gathering ở đó, thời điểm nó thường hình thành "
      "(giây sau khi bo trắng xuất hiện) và rủi ro bị loại so với baseline. Tham số mặc định, "
      f"{n_matches} trận.")
    if G.empty:
        verdict("Chưa có gathering.", False)
    else:
        a, b = st.columns(2)
        phases = sorted(int(p) for p in G["phase"].unique())
        ph = a.selectbox("Phase", phases, index=min(2, len(phases) - 1), format_func=lambda p: f"Phase {p}")
        places = G[G["phase"] == ph]["place"].value_counts()
        place = b.selectbox("Địa điểm", list(places.index), format_func=lambda p: f"{p} ({places[p]} gathering)")
        g = G[(G["phase"] == ph) & (G["place"] == place)]
        m_with = g["match_id"].nunique()
        pct = 100 * m_with / max(n_matches, 1)
        q25, q75 = np.percentile(g["t_after_zone"], [25, 75]) if len(g) else (np.nan, np.nan)
        e = E[(E["level"] == "player") & (E["phase"] == ph) & (E["place"] == place)]
        rp = e[e["group"] == "participator"]["eliminated"]
        rb = E[(E["level"] == "player") & (E["phase"] == ph) & (E["group"] == "baseline")]["eliminated"]
        c = st.columns(4)
        c[0].metric("Trận có gathering", f"{pct:.0f}%", help=f"{m_with}/{n_matches} trận")
        c[1].metric("Hình thành sau bo", f"{q25:.0f}–{q75:.0f} s" if len(g) else "—", help="khoảng tứ phân vị 25–75%")
        c[2].metric("Bị loại (participator)", f"{100 * rp.mean():.0f}%" if len(rp) else "—", help=f"n = {len(rp)}")
        c[3].metric("Bị loại (baseline phase)", f"{100 * rb.mean():.0f}%" if len(rb) else "—", help=f"n = {len(rb)}")
        if len(rp) and len(rb) and rb.mean() > 0:
            rel = 100 * (rp.mean() / rb.mean() - 1)
            word = "cao hơn" if rel >= 0 else "thấp hơn"
            sent = (f"Ở <b>phase {ph}</b>, <b>{place}</b> có gathering trong <b>{pct:.0f}%</b> số trận, thường hình thành "
                    f"<b>{q25:.0f}–{q75:.0f} s</b> sau khi bo xuất hiện; người ở trong đám đông đó bị loại trong vòng 120 s "
                    f"sau khi nó tan với tỉ lệ <b>{100 * rp.mean():.0f}%</b>, <b>{abs(rel):.0f}% {word}</b> baseline cùng phase "
                    f"({100 * rb.mean():.0f}%) — n = {len(rp)} lượt participator / {len(rb)} lượt baseline.")
            verdict(sent, rel < 0)
            if len(rp) < 30:
                st.caption("⚠️ Mẫu nhỏ (n < 30) — chỉ nên xem là gợi ý.")
        st.caption(f"{src} Tương quan, không phải nhân quả: vòng bo ngẫu nhiên và kỹ năng đội khác nhau.")

with tab2:
    q("Chọn một trận và một đội → các khoảnh khắc đội nằm trong một gathering, ai là participator và kết quả "
      "(an toàn / mất người / bị loại cả đội trong ≤ 120 s). Dùng cột <b>VOD</b> để tua video.")
    t = common.load_match(ctx["folder"], ctx["match_id"])
    res, gdf = mine_one(t, ctx["params"])
    teams = sorted(t["positions"]["team"].unique())
    in_g = {tm for ts in gdf["teams"] for tm in ts} if len(gdf) else set()
    rank = dict(zip(t["results"]["team"], t["results"]["ranking"], strict=True))
    team = st.selectbox("Đội", teams, index=teams.index(sorted(in_g)[0]) if in_g else 0,
                        format_func=lambda tm: f"{tm} · hạng {rank.get(tm, '?')}{' · có gathering' if tm in in_g else ''}")
    rep = team_report(t, res, gdf, team)
    if rep.empty:
        verdict(f"{team} không nằm trong gathering nào ở trận này (tham số hiện tại).", True)
    else:
        st.dataframe(rep.drop(columns=["t_start", "t_end"]).rename(columns={
            "vod_start": "VOD từ", "vod_end": "đến", "place": "địa điểm", "zone": "vị trí so với bo",
            "members_present": "thành viên có mặt", "participators": "participator", "outcome": "kết quả",
            "eliminated": "bị loại"}), hide_index=True, width="stretch")
        st.download_button("⬇️ Xuất CSV mốc thời gian", rep.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"vod_{ctx['match_id']}_{team}.csv", mime="text/csv")
    st.caption(f"{src} Hạng cuối của {team}: {rank.get(team, '?')}.")
