"""🎮 Trận đấu — giá trị cho HLV trước (kết luận + VOD), bằng chứng sau (di chuyển, xoay bo, chạm trán)."""
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

from src.analytics.coach import losses, match_insights, vod_flags  # noqa: E402
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


@st.cache_data(show_spinner=False, max_entries=8)
def _insights(folder: str, mid: str) -> list[dict]:
    tb = common.load_match(folder, mid)
    r = common.mine(folder, mid, common.params_key(default_params()))
    return match_insights(tb, r, _summary(folder, mid)[0], r.gathering_df)


@st.cache_data(show_spinner=False, max_entries=64)
def _vod(folder: str, mid: str, team: str) -> pd.DataFrame:
    tb = common.load_match(folder, mid)
    r = common.mine(folder, mid, common.params_key(default_params()))
    return vod_flags(tb, r, r.gathering_df, team)


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
insights = _insights(folder, mid)
gby = {int(r.id): r for r in gdf.itertuples()} if len(gdf) else {}


def gname(gid: int) -> str:
    return f"G{gid + 1} · {gby[gid].place}"


# ---------------- header: where the value comes from ----------------
st.title("🎮 Trận đấu: từ quỹ đạo đến bài tập cho HLV")
n_flags = sum(len(_vod(folder, mid, tm)) for tm in summary["team"])
steps = [("", f"{pos['player'].nunique()}", "người chơi"), ("", f"{len(pos) / 1000:.1f}k", "điểm (x, y, t)"),
         ("mine", f"{len(res.clusters)}", "cụm DBSCAN"), ("mine", f"{len(res.crowds)}", "crowd"),
         ("mine", f"{len(gdf)}", "gathering"), ("value", f"{len(insights)}", "kết luận cho HLV"),
         ("value", f"{n_flags}", "mốc VOD cần xem lại")]
html = '<span class="arrow">→</span>'.join(f'<div class="step {c}"><b>{v}</b><span>{lb}</span></div>'
                                            for c, v, lb in steps)
st.markdown(f'<div class="vchain">{html}</div>', unsafe_allow_html=True)
a, b = st.columns([4, 1])
a.caption("Dữ liệu → **khai phá (xanh)** → **giá trị (cam)**: mỗi kết luận và mỗi mốc VOD đều trỏ về gathering "
          "mà thuật toán tìm ra.")
b.page_link("views/algorithm.py", label="Mining từng bước →", icon="🔬")

default = [tm for tm in default_focus(summary) if tm in label]
focus = st.multiselect("Đội theo dõi (tối đa 4)", list(summary["team"]), default=default, max_selections=MAX_FOCUS,
                       format_func=lambda tm: label[tm], key=f"focus_{mid}")
colors = dict(zip(focus, FOCUS_COLORS, strict=False))


def dot(tm: str) -> str:
    return f'<span style="color:{colors.get(tm, "#888")};font-size:18px">●</span>'


# ---------------- one encounter (evidence), reused by every tab ----------------
def render_encounter(gid: int, key: str, height: int = 560) -> None:
    row = gby[gid]
    cs = [res.clusters[i] for i in row.clusters]
    allp = np.vstack([cl.pts for cl in cs])
    lo, hi = allp.min(0), allp.max(0)
    view = zoom_box(*(lo + hi) / 2, max(hi - lo) / 2 + 250, pad=1.2, min_half=450)
    t0, t1 = row.t_start - 60, row.t_end + 60
    teams = list(row.teams)
    others_c = iter(OTHER_COLORS * 3)
    tcol = {tm: colors.get(tm) or next(others_c) for tm in teams}
    win = pos[pos["team"].isin(teams) & pos["t"].between(t0, t1)].sort_values(["player", "t"])
    kw = kills[kills["t"].between(t0, t1 + 60) & kills["x"].between(view[0], view[2])
               & kills["y"].between(view[1], view[3])]
    left, right = st.columns([3, 2])
    with right:
        mode = st.segmented_control("Kiểu xem", ["3D", "2D"], default="3D", key=f"encm_{key}") or "3D"
        lo_ = losses(t, row)
        items = []
        for tm in sorted(teams, key=lambda x: info.loc[x, "rank"]):
            mine = [p for p in lo_["lost_players"] if p in set(pos.loc[pos["team"] == tm, "player"])]
            out = ("<b>bị xoá sổ</b>" if tm in lo_["wiped"] else f"mất {len(mine)}" if mine else "an toàn")
            items.append(f"<li><span style='color:{tcol[tm]}'>●</span> <b>{tm}</b> (hạng {info.loc[tm, 'rank']})"
                         f" → {out}</li>")
        verdict(f"<b>{gname(gid)}</b> · phase {int(row.phase)} · {fmt_t(row.t_start)}–{fmt_t(row.t_end)} · "
                f"{len(teams)} đội · {int(row.n_participators)} participator<ul style='margin:6px 0 0'>"
                f"{''.join(items)}</ul>Trong lúc + 2 phút sau: <b>{lo_['lost']}/{lo_['present']} người bị loại</b>",
                lo_["lost"] == 0)
    with left:
        if mode == "3D":
            lines = [dict(df=win[win["team"] == tm], color=tcol[tm], width=7 if tm in colors else 4, name=label[tm],
                          legend=True) for tm in teams]
            discs = [dict(pts=cl.pts, t=cl.t, color=ORANGE, opacity=0.3, hover=f"{fmt_t(cl.t)} · {cl.size} người")
                     for cl in cs]
            pts = [dict(x=r_.x, y=r_.y, t=r_.t, color="#ff2d55", symbol="x", size=5,
                        hover=f"✖ {r_.victim} ({r_.victim_team}) · {fmt_t(r_.t)}") for r_ in kw.itertuples()]
            fig = space_time_cube(view, t0, t1 + 60, lines=lines, discs=discs, points=pts, height=height,
                                  rev=f"enc_{key}_{gid}")
        else:
            fig = base_map(height, view, dim=0.3)
            place_labels(fig, size=12)
            for j, cl in enumerate(cs):
                fig.add_trace(hull_trace(cl.pts, "#ffffff", opacity=0.04 + 0.25 * (j + 1) / len(cs), width=0.5))
            for tm in teams:
                xs, ys = [], []
                for _, p in win[win["team"] == tm].groupby("player"):
                    xs += list(p["x"]) + [None]
                    ys += list(p["y"]) + [None]
                fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name=label[tm], hoverinfo="name",
                                         line=dict(color=tcol[tm], width=3.5 if tm in colors else 2)))
            fig.add_trace(go.Scatter(x=kw["x"], y=kw["y"], mode="markers", name="bị loại", hoverinfo="text",
                                     marker=dict(size=14, symbol="x", color="#ff2d55", line=dict(width=1, color="white")),
                                     hovertext=[f"✖ {v} ({vt}) · {fmt_t(tt)}" for v, vt, tt in
                                                zip(kw["victim"], kw["victim_team"], kw["t"], strict=True)]))
            fig.add_annotation(x=row.cx, y=view[1] + 0.06 * (view[3] - view[1]), showarrow=False,
                               text=f"<b>{gname(gid)}</b>", font=dict(color="white", size=14, shadow=TEXT_SHADOW))
            fig.update_layout(shapes=zone_shapes(zones, row.t_end), margin=dict(l=0, r=0, t=10, b=0),
                              legend=dict(orientation="h", y=0, yanchor="top"))
        st.plotly_chart(fig, width="stretch", key=f"encfig_{key}_{gid}")


tabs = st.tabs(["💡 Kết luận cho HLV", "🎬 VOD cần xem lại", "🗺️ Di chuyển", "🔄 Xoay bo", "⚔️ Chạm trán"])

# ---------------- 💡 insights ----------------
with tabs[0]:
    if not insights:
        verdict("Không có gathering nào → chưa rút ra được kết luận.", False)
    for i in range(0, len(insights), 2):
        cols = st.columns(2)
        for col, ins in zip(cols, insights[i:i + 2], strict=False):
            with col.container(border=True):
                st.markdown(f'<div class="card-title">{ins["icon"]} {ins["title"]}</div>'
                            f'<div class="card-big">{ins["big"]}<small>{ins["big_label"]}</small></div>'
                            f'<div class="card-detail">{ins["detail"]}</div>'
                            f'<div class="advice">👉 <b>HLV:</b> {ins["advice"]}</div>'
                            f'<div class="evidence">Bằng chứng (gathering đã khai phá): '
                            f'{", ".join(gname(g) for g in ins["evidence"] if g in gby) or "—"}</div>',
                            unsafe_allow_html=True)
                ev = [g for g in ins["evidence"] if g in gby]
                if ev:
                    with st.expander(f"Xem bằng chứng: {gname(ev[0])}"):
                        render_encounter(ev[0], f"ins_{ins['key']}", height=460)
    st.caption("Mock data · 1 trận → minh hoạ phương pháp. Kết luận thật cần nhiều trận thật (tương quan, không phải "
               "nhân quả).")

# ---------------- 🎬 VOD flags ----------------
with tabs[1]:
    teams_sorted = list(summary["team"])
    vteam = st.selectbox("Đội", teams_sorted, index=teams_sorted.index(focus[0]) if focus else 0,
                         format_func=lambda tm: label[tm], key=f"vod_team_{mid}")
    vod = _vod(folder, mid, vteam)
    if vod.empty:
        verdict(f"<b>{vteam}</b> không dính chạm trán nào — không có mốc cần xem lại.", None)
    else:
        mins = (vod["t_end"] - vod["t_start"] + 10).sum() / 60 + 2 * len(vod)
        verdict(f"<b>{vteam}</b> (hạng {info.loc[vteam, 'rank']}): <b>{len(vod)} khoảnh khắc</b> cần xem lại "
                f"(≈ {mins:.0f} phút VOD thay vì {T_END // 60} phút cả trận). Chọn một dòng để xem lại trên bản đồ.")
        show = pd.DataFrame({
            "Mốc VOD": vod["vod_start"] + "–" + vod["vod_end"], "Gathering": vod["gathering"],
            "Địa điểm": vod["place"], "Phase": vod["phase"], "Gặp đội": vod["teams_met"],
            "Có mặt": vod["members_present"], "Participator": vod["participators"], "Kết cục": vod["outcome"],
            "Bị loại": vod["eliminated"]})
        ev = st.dataframe(show, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                          key=f"vod_tab_{mid}_{vteam}")
        st.download_button("⬇ Tải CSV (mốc VOD)", vod.drop(columns=["gid"]).to_csv(index=False).encode("utf-8-sig"),
                           f"vod_{mid}_{vteam}.csv", "text/csv", key="vod_csv")
        rows = getattr(getattr(ev, "selection", None), "rows", []) or [0]
        render_encounter(int(vod.loc[rows[0], "gid"]), "vod")

# ---------------- 🗺️ movement ----------------
with tabs[2]:
    view = st.segmented_control("Xem", ["Đường đi", "Replay", "3D x–y–t"], default="Đường đi",
                                key="move_view") or "Đường đi"
    if focus:
        st.markdown(" ".join(f'<span class="badge" style="background:{colors[tm]};color:#111">{label[tm]}</span>'
                             for tm in focus), unsafe_allow_html=True)
    if view == "Đường đi":
        st.plotly_chart(team_routes(tracks, summary, focus, colors, zones), width="stretch")
        for tm in focus:
            r = info.loc[tm]
            end = "còn sống" if r["survived"] else f"loại {fmt_t(r['out_t'])} · {r['out_place']}"
            st.markdown(f"{dot(tm)} **{tm}** (hạng {r['rank']}): {r['route_str']} · {end} · {r['dist_km']:.1f} km",
                        unsafe_allow_html=True)
    elif view == "Replay":
        a, b = st.columns([2, 1])
        follow = a.selectbox("Bám theo đội", [None] + focus, key=f"follow_{mid}",
                             format_func=lambda tm: "— toàn bản đồ —" if tm is None else label[tm])
        speed = b.radio("Tốc độ", ["Chậm", "Vừa", "Nhanh"], index=1, horizontal=True, key="speed")
        st.plotly_chart(_replay(folder, mid, tuple(focus), follow, {"Chậm": 450, "Vừa": 250, "Nhanh": 120}[speed]),
                        width="stretch")
    else:
        a, b, c3 = st.columns([3, 1, 1])
        t_range = a.slider("Khoảng thời gian", 0, T_END, (0, T_END), step=10, format="%d s", key=f"cube_t_{mid}")
        others = b.toggle("Đội khác", value=True, key="cube_others")
        gath = c3.toggle("Chạm trán", value=True, key="cube_gath")
        st.plotly_chart(_team_cube(folder, mid, tuple(focus), tuple(t_range), others, gath), width="stretch")
        st.caption(f"{fmt_t(t_range[0])} → {fmt_t(t_range[1])} · trục đứng = thời gian · cột cam = gathering")

# ---------------- 🔄 rotation ----------------
with tabs[3]:
    order = focus + [tm for tm in summary["team"] if tm not in focus]
    tab = summary.set_index("team").loc[order].reset_index()
    show = pd.DataFrame({
        "Đội": tab["team"], "Hạng": tab["rank"], "Lộ trình (đầu mỗi phase)": tab["route_str"],
        "Kết cục": [("còn sống" if s else f"loại {fmt_t(o)} · {p}")
                    for s, o, p in zip(tab["survived"], tab["out_t"], tab["out_place"], strict=True)],
        "km": tab["dist_km"].round(1), "Chạm trán": tab["n_gatherings"],
        "Ngoài bo (s)": tab["outside_s"].astype(int)})

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
        zf.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10), yaxis_title="m tới mép bo (> 0: ngoài bo)",
                         xaxis=dict(tickvals=ticks, ticktext=[fmt_t(x) for x in ticks], title=None),
                         legend=dict(orientation="h", y=1.15), plot_bgcolor="#FBF8F1")
        st.plotly_chart(zf, width="stretch")

# ---------------- ⚔️ encounters ----------------
with tabs[4]:
    if gdf.empty:
        verdict("Không có gathering nào.", False)
    else:
        g = gdf.sort_values("t_start").reset_index(drop=True)
        star = [any(tm in focus for tm in teams) for teams in g["teams"]]
        phase_col = ["#9ecae1", "#6baed6", "#4292c6", "#2171b5", "#fdae6b", "#fd8d3c", "#e6550d", "#a63603",
                     "#7f2704"]
        names = [gname(int(i)) for i in g["id"]]
        gt = go.Figure(go.Bar(
            y=[("★ " if s else "") + n for n, s in zip(names, star, strict=True)], x=g["t_end"] - g["t_start"] + 10,
            base=g["t_start"], orientation="h", marker_color=[phase_col[min(int(p), 8)] for p in g["phase"]],
            text=[f"{len(teams)} đội" for teams in g["teams"]], textposition="inside", hoverinfo="text",
            hovertext=[f"{n} · {fmt_t(a)}–{fmt_t(b)} · phase {p} · {', '.join(teams)}" for n, a, b, p, teams
                       in zip(names, g["t_start"], g["t_end"], g["phase"], g["teams"], strict=True)]))
        ticks = list(range(0, T_END + 1, 180))
        gt.update_layout(height=60 + 34 * len(g), margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="#FBF8F1",
                         xaxis=dict(tickvals=ticks, ticktext=[fmt_t(x) for x in ticks], range=[0, T_END]),
                         yaxis=dict(autorange="reversed"))
        st.plotly_chart(gt, width="stretch")
        best = int(np.argmax([sum(tm in focus for tm in teams) for teams in g["teams"]])) if focus else 0
        k = st.selectbox("Chạm trán", list(range(len(g))), index=best, key=f"enc_{mid}",
                         format_func=lambda i: f"{'★ ' if star[i] else ''}{names[i]} · {fmt_t(g.loc[i, 't_start'])}–"
                         f"{fmt_t(g.loc[i, 't_end'])} · {len(g.loc[i, 'teams'])} đội")
        render_encounter(int(g.loc[k, "id"]), "enc")
