"""Shared app helpers: paths, CSS, sidebar (source badge, match picker, §3 parameters), cached loaders."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.analytics.gazetteer import nearest_place  # noqa: E402
from src.config import default_params, path  # noqa: E402
from src.mining.pipeline import PARAM_KEYS, MiningResult, run_pipeline  # noqa: E402
from src.parse.telemetry import read_tables  # noqa: E402

INK, PAPER, LINE, RUST = "#172033", "#FBF8F1", "#D8D0BE", "#B8541C"
ICE, PEACH = "#E3F0F7", "#FBE3D6"
SOURCE_LABEL = {"mock": "MOCK DATA", "real": "REAL PUBG DATA", "pubg": "REAL PUBG DATA"}

PARAM_UI = {  # key: (label, min, max, step, help)
    "eps": ("eps — bán kính DBSCAN (m)", 50, 400, 10, "Hai người cách nhau ≤ eps là hàng xóm."),
    "min_pts": ("min_pts — DBSCAN", 2, 8, 1, "Số hàng xóm tối thiểu của một điểm lõi."),
    "m_c": ("m_c — cỡ cụm tối thiểu", 4, 30, 1, "Mỗi cụm của Crowd phải có ≥ m_c người (≥ 2 squad)."),
    "delta": ("δ — Hausdorff tối đa (m)", 100, 800, 10, "Hai cụm liên tiếp cách nhau (Hausdorff) ≤ δ."),
    "k_c": ("k_c — thời gian sống (bước Δt)", 3, 30, 1, "Crowd kéo dài ≥ k_c bước (10 s/bước)."),
    "k_p": ("k_p — số bước để là Participator", 2, 30, 1, "Có mặt ở ≥ k_p cụm của crowd."),
    "m_p": ("m_p — participator mỗi cụm", 3, 30, 1, "Mỗi cụm của Gathering có ≥ m_p participator."),
}

CSS = f"""<style>
.block-container {{ padding-top: 2.6rem; max-width: 1400px; }}
.kicker {{ color: {RUST}; font-weight: bold; font-size: 13px; letter-spacing: .05em; }}
.q {{ background: {PAPER}; border: 1px solid {LINE}; border-left: 5px solid {INK}; border-radius: 8px;
      padding: 10px 14px; margin: 4px 0 12px; font-size: 16px; line-height: 1.5; }}
.verdict {{ border-radius: 10px; padding: 10px 14px; margin: 6px 0 10px; line-height: 1.5; border: 1px solid {LINE}; }}
.verdict.yes {{ background: {ICE}; }} .verdict.no {{ background: {PEACH}; }}
.badge {{ display: inline-block; border-radius: 6px; padding: 3px 10px; font-weight: bold; font-size: 13px;
          color: #fff; letter-spacing: .04em; }}
.badge.mock {{ background: #8a5a00; }} .badge.real {{ background: #1f7a3a; }}
</style>"""


def page(title: str, icon: str) -> None:
    st.set_page_config(page_title=title, page_icon=icon, layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)


def q(html: str) -> None:
    st.markdown(f'<div class="q">{html}</div>', unsafe_allow_html=True)


def verdict(html: str, ok: bool | None = None) -> None:
    cls = "" if ok is None else ("yes" if ok else "no")
    st.markdown(f'<div class="verdict {cls}">{html}</div>', unsafe_allow_html=True)


# ---------------- data discovery ----------------
def source_dirs() -> dict[str, Path]:
    """source → folder with processed matches. data/processed/{src} wins over data/sample/{src}."""
    out: dict[str, Path] = {}
    for base in (path("sample"), path("processed")):
        if not base.exists():
            continue
        for d in sorted(base.iterdir()):
            if d.is_dir() and any((m / "meta.json").exists() for m in d.iterdir() if m.is_dir()):
                out["real" if d.name == "pubg" else d.name] = d
    return out


@st.cache_data(show_spinner=False)
def match_table(folder: str) -> pd.DataFrame:
    rows = []
    for m in sorted(Path(folder).iterdir()):
        if (m / "meta.json").exists():
            rows.append(json.loads((m / "meta.json").read_text(encoding="utf8")))
    return pd.DataFrame(rows)


@st.cache_data(show_spinner="Đang đọc dữ liệu trận…", max_entries=8)
def load_match(folder: str, match_id: str) -> dict:
    return read_tables(Path(folder) / match_id)


@st.cache_data(show_spinner="Đang khai phá (DBSCAN → Crowd → TAD)…", max_entries=32)
def mine(folder: str, match_id: str, params_items: tuple) -> MiningResult:
    res = run_pipeline(load_match(folder, match_id), dict(params_items))
    for df in (res.crowd_df, res.gathering_df):
        if len(df):
            df["place"] = [nearest_place(x, y) for x, y in zip(df["cx"], df["cy"], strict=True)]
    return res


@st.cache_data(show_spinner=False)
def load_aggregates(folder: str) -> dict | None:
    """Precomputed multi-match aggregates (scripts/build_sample.py) for the default parameters."""
    f = Path(folder) / "_aggregates"
    if not (f / "gatherings.parquet").exists():
        return None
    out = {p.stem: pd.read_parquet(p) for p in f.glob("*.parquet")}
    if (f / "info.json").exists():
        out["info"] = json.loads((f / "info.json").read_text())
    return out


# ---------------- sidebar ----------------
def showcase_match() -> str | None:
    from src.config import load_config

    return (load_config().get("app") or {}).get("showcase_match")


def _reset_params() -> None:
    for k, v in default_params().items():
        st.session_state[f"p_{k}"] = v
    st.session_state["_params"] = default_params()


def sidebar(match_picker: bool = True, params: bool = True) -> dict:
    """Render the shared sidebar. Returns dict(source, folder, match_id, params, meta)."""
    srcs = source_dirs()
    st.sidebar.markdown("### 🎯 Gathering · PUBG")
    if not srcs:
        st.sidebar.error("Không có dữ liệu. Chạy `scripts/build_sample.py` hoặc pipeline (README).")
        st.stop()
    names = list(srcs)
    default = "real" if "real" in srcs else names[0]
    if len(names) == 1:
        src = names[0]
    else:
        src = st.sidebar.selectbox("Nguồn dữ liệu", names, index=names.index(st.session_state.get("source", default))
                                   if st.session_state.get("source", default) in names else 0, key="source",
                                   format_func=lambda s: SOURCE_LABEL.get(s, s))
    cls = "real" if src in ("real", "pubg") else "mock"
    st.sidebar.markdown(f'<span class="badge {cls}">{SOURCE_LABEL.get(src, src)}</span>', unsafe_allow_html=True)
    folder = str(srcs[src])
    mt = match_table(folder)
    out = dict(source=src, folder=folder, matches=mt, match_id=None, params=default_params(), meta=None)
    if len(mt) == 1:  # the demo ships one match: no picker, just what it is
        r = mt.iloc[0]
        out["match_id"], out["meta"] = r["match_id"], r.to_dict()
        st.sidebar.caption(f"`{r['match_id']}` · Erangel · {r['gameMode']} · {r['n_teams']} đội · "
                           f"{int(r['duration']) // 60}:{int(r['duration']) % 60:02d}")
    elif match_picker and len(mt):
        ids = list(mt["match_id"])
        short = lambda m: m if len(m) <= 16 else "…" + m[-10:]  # noqa: E731
        lab = {r.match_id: f"{short(r.match_id)} · {str(r.createdAt)[:10]} · {r.gameMode}"
               + (" ★" if r.match_id == showcase_match() else "") for r in mt.itertuples()}
        # widget keys are dropped on pages that don't render them, so remember the choice separately
        cur = st.session_state.get("_match_id")
        if cur not in ids:
            cur = showcase_match() if showcase_match() in ids else ids[0]
        if st.session_state.get("match_id") not in ids:
            st.session_state["match_id"] = cur
        mid = st.sidebar.selectbox("Trận", ids, format_func=lambda m: lab[m], key="match_id")
        st.session_state["_match_id"] = mid
        out["match_id"] = mid
        out["meta"] = mt.set_index("match_id").loc[mid].to_dict()
    if params:
        st.sidebar.markdown("#### Tham số thuật toán")
        saved = st.session_state.get("_params", {})
        for k, v in default_params().items():
            st.session_state.setdefault(f"p_{k}", saved.get(k, v))
        vals = {}
        for k in PARAM_KEYS:
            label, lo, hi, step, hlp = PARAM_UI[k]
            if k == "k_p":
                hi = vals["k_c"]
            if k == "m_p":
                hi = vals["m_c"]
            if st.session_state[f"p_{k}"] > hi:
                st.session_state[f"p_{k}"] = hi
            if st.session_state[f"p_{k}"] < lo:
                st.session_state[f"p_{k}"] = lo
            if lo >= hi:
                st.sidebar.caption(f"{label}: {hi} (bị chặn bởi ràng buộc)")
                vals[k] = hi
                continue
            vals[k] = st.sidebar.slider(label, lo, hi, step=step, key=f"p_{k}", help=hlp)
        st.sidebar.button("↺ Về mặc định", on_click=_reset_params)
        st.sidebar.caption("Ràng buộc: k_p ≤ k_c, m_p ≤ m_c. Δt = 10 s.")
        st.session_state["_params"] = dict(vals)
        out["params"] = vals
    return out


def caption_source(ctx: dict) -> str:
    return f"[{SOURCE_LABEL.get(ctx['source'], ctx['source'])}]"


def params_key(p: dict) -> tuple:
    return tuple(sorted(p.items()))


@st.cache_data(show_spinner="Đang tổng hợp nhiều trận (chạy pipeline trên từng trận)…", max_entries=4)
def compute_aggregates(folder: str, params_items: tuple) -> dict:
    from src.analytics.aggregate import aggregate

    return aggregate(Path(folder), dict(params_items))


def aggregates(ctx: dict, use_sidebar: bool) -> tuple[dict, dict]:
    """Precomputed aggregates at default params when available, else computed (cached)."""
    params = ctx["params"] if use_sidebar else default_params()
    pre = load_aggregates(ctx["folder"])
    if pre is not None and pre.get("info", {}).get("params") == params:
        return pre, params
    return compute_aggregates(ctx["folder"], params_key(params)), params
