"""Coach takeaways for one match, built only from the mined gatherings: insight cards and VOD flags.

Every insight cites the gatherings it comes from (evidence), so the UI can show where the value comes from.
One match = an illustration of the method, not a conclusion about PUBG (the UI says so).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.analytics.gazetteer import places
from src.analytics.outcomes import kill_inout
from src.analytics.team_report import team_report
from src.analytics.zone import annotate_zone
from src.viz.map_plot import fmt_t

WINDOW = 120.0  # seconds after a gathering that still count as "what happened next"


def losses(tables: dict, row, window: float = WINDOW) -> dict:
    """Players of the gathering's teams eliminated during it or ≤ window s after, and teams wiped by then."""
    pos, kills = tables["positions"], tables["kills"]
    death = kills.groupby("victim")["t"].min()
    teams = list(row.teams)
    mem = pos.loc[pos["team"].isin(teams), ["player", "team"]].drop_duplicates()
    alive = mem[[death.get(p, np.inf) >= row.t_start for p in mem["player"]]]
    lost = [p for p in alive["player"] if death.get(p, np.inf) <= row.t_end + window]
    wiped = [tm for tm, g in alive.groupby("team") if len(g) and all(p in lost for p in g["player"])]
    return dict(present=len(alive), lost=len(lost), lost_players=lost, wiped=sorted(wiped), teams=teams)


def _name(row) -> str:
    return f"G{int(row.id) + 1} · {row.place}"


def _span(row) -> str:
    return f"{fmt_t(row.t_start)}–{fmt_t(row.t_end)}"


def _wiped_txt(w: list[str]) -> str:
    return f"; {', '.join(w)} bị xoá sổ" if w else ""


def match_insights(tables: dict, res, summary: pd.DataFrame, gdf: pd.DataFrame) -> list[dict]:
    """Up to 4 cards: hot_drop, winner_route, chokepoint, danger_rate (skipped when the data is missing)."""
    out: list[dict] = []
    if gdf is None or gdf.empty:
        return out
    g = gdf.sort_values("t_start")
    L = {int(r.id): losses(tables, r) for r in g.itertuples()}
    rank = summary.set_index("team")["rank"]

    # 1. early hot drops
    early = g[g["phase"] <= 1]
    if len(early):
        worst = max(early.itertuples(), key=lambda r: (L[int(r.id)]["lost"], len(r.teams)))
        lw = L[int(worst.id)]
        caught = {tm for teams in early["teams"] for tm in teams}
        a = rank[rank.index.isin(caught)]
        b = rank[~rank.index.isin(caught)]
        cmp = (f" Đội dính chạm trán đầu trận về <b>hạng TB {a.mean():.1f}</b> (n={len(a)}) so với "
               f"<b>{b.mean():.1f}</b> (n={len(b)}) ở các đội còn lại.") if len(a) and len(b) else ""
        out.append(dict(
            key="hot_drop", icon="🪂", title="Hot drop đầu trận rất đắt", big=f"{lw['lost']}/{lw['present']}",
            big_label="người bị loại",
            detail=f"<b>{_name(worst)}</b> ({_span(worst)}): {len(worst.teams)} đội nhảy chung, {lw['lost']}/"
                   f"{lw['present']} người bị loại trong lúc đó và 2 phút sau{_wiped_txt(lw['wiped'])}.{cmp}",
            advice="Chọn điểm nhảy ít đội tranh. Nếu buộc phải hot drop: tập phương án tiếp đất – nhặt súng – "
                   "đánh cận chiến, và chấp nhận rủi ro mất nửa đội.",
            evidence=[int(r.id) for r in sorted(early.itertuples(), key=lambda r: -L[int(r.id)]["lost"])]))

    # 2. the winner's route
    if len(summary):
        w = summary.sort_values("rank").iloc[0]
        mine = g[[w["team"] in teams for teams in g["teams"]]]
        early_w = bool(len(mine) and (mine["phase"] <= 1).any())
        if len(mine):
            f = mine.iloc[0]
            first = f"chạm trán đầu tiên ở <b>{f['place']}</b> lúc {fmt_t(f['t_start'])} (phase {int(f['phase'])})"
        else:
            first = "không dính chạm trán nào"
        detail = (f"Nhảy <b>{w['land_place']}</b>{' (dính hot drop)' if early_w else ' — tránh hot drop'}, "
                  f"{first}, tổng {len(mine)} lần chạm trán → vô địch. Lộ trình: {w['route_str']}.")
        advice = ("Loot ở nơi yên tĩnh, vào giao tranh theo thời điểm của mình — không để bo hay đội khác ép."
                  if not early_w else "Thắng được hot drop thì phải xoay bo sớm để không bị kẹp ở điểm nghẽn.")
        out.append(dict(key="winner_route", icon="🏆", title="Đội vô địch đã đi thế nào", big=w["team"],
                        big_label=f"vô địch · {w['dist_km']:.1f} km", detail=detail, advice=advice,
                        evidence=[int(i) for i in mine["id"]]))

    # 3. chokepoints (bridges), else the deadliest mid-game gathering
    bridges = {p["name"] for p in places() if p.get("kind") == "bridge"}
    choke = g[g["place"].isin(bridges)]
    if choke.empty:
        choke = g[g["phase"].between(2, 5)]
    if len(choke):
        c = max(choke.itertuples(), key=lambda r: L[int(r.id)]["lost"])
        lc = L[int(c.id)]
        is_bridge = c.place in bridges
        out.append(dict(
            key="chokepoint", icon="🌉" if is_bridge else "⚠️",
            title="Điểm nghẽn là cái bẫy" if is_bridge else "Giao tranh giữa trận tốn kém",
            big=f"{lc['lost']}/{lc['present']}", big_label="người bị loại",
            detail=f"<b>{_name(c)}</b>, phase {int(c.phase)} ({_span(c)}): {len(c.teams)} đội dồn vào, "
                   f"{lc['lost']}/{lc['present']} người bị loại trong lúc đó và 2 phút sau{_wiped_txt(lc['wiped'])}.",
            advice="Qua cầu / điểm nghẽn sớm, trước khi bo ép và trước khi đội khác kịp chốt; hoặc đổi tuyến. "
                   "Xem lại VOD: đội nào chốt từ lúc nào, mình vào lúc nào.",
            evidence=[int(r.id) for r in sorted(choke.itertuples(), key=lambda r: -L[int(r.id)]["lost"])]))

    # 4. risk inside crowds
    ki = kill_inout(tables, res, gdf)
    if ki["pmin_inside"] > 0 and ki["pmin_outside"] > 0:
        r_in = ki["kills_inside"] / ki["pmin_inside"]
        r_out = ki["kills_outside"] / ki["pmin_outside"]
        ratio = r_in / r_out if r_out > 0 else np.inf
        out.append(dict(
            key="danger_rate", icon="☠️", title="Đứng trong đám đông = dễ chết", big=f"×{ratio:.1f}",
            big_label="tỉ lệ bị loại",
            detail=f"<b>{r_in:.2f}</b> lượt bị loại / người·phút <b>trong</b> gathering so với <b>{r_out:.2f}</b> ở "
                   f"ngoài ({ki['kills_inside']} vs {ki['kills_outside']} lượt; {ki['pmin_inside']:.0f} vs "
                   f"{ki['pmin_outside']:.0f} người·phút).",
            advice="Giảm thời gian đứng trong đám đông nếu không chủ động đánh; tập tín hiệu rút lui khi quanh mình "
                   "có ≥ 3 đội.",
            evidence=[int(i) for i in sorted(L, key=lambda i: -L[i]["lost"])[:3]]))
    return out


VOD_COLUMNS = ["gid", "gathering", "vod_start", "vod_end", "phase", "place", "teams_met", "members_present",
               "participators", "outcome", "eliminated"]


def vod_flags(tables: dict, res, gdf: pd.DataFrame, team: str) -> pd.DataFrame:
    """Moments to re-watch for one team: every gathering it was in, with who it met and what happened next."""
    if gdf is None or gdf.empty:
        return pd.DataFrame(columns=VOD_COLUMNS)
    g = annotate_zone(gdf, tables["zones"]) if "zone_label" not in gdf else gdf
    rep = team_report(tables, res, g, team)
    if rep.empty:
        return pd.DataFrame(columns=VOD_COLUMNS)
    rep["gid"] = rep["gathering"].str[1:].astype(int) - 1
    teams_of = dict(zip(g["id"].astype(int), g["teams"], strict=True))
    rep["teams_met"] = [", ".join(tm for tm in teams_of.get(i, []) if tm != team) or "—" for i in rep["gid"]]
    return rep.sort_values("t_start")[VOD_COLUMNS + ["t_start", "t_end"]].reset_index(drop=True)
