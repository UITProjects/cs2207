"""Shared app helpers: paths, CSS, sidebar (source badge, match info, §3 parameters), cached loaders."""
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
from src.config import default_params, load_config, path  # noqa: E402
from src.mining.pipeline import PARAM_KEYS, MiningResult, run_pipeline  # noqa: E402
from src.parse.telemetry import read_tables  # noqa: E402

INK, PAPER, LINE, RUST = "#172033", "#FBF8F1", "#D8D0BE", "#B8541C"
ICE, PEACH = "#E3F0F7", "#FBE3D6"

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
.vchain {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 2px 0 10px; }}
.vchain .step {{ background: {PAPER}; border: 1px solid {LINE}; border-radius: 10px; padding: 6px 12px;
                 line-height: 1.2; text-align: center; }}
.vchain .step b {{ display: block; font-size: 22px; color: {INK}; }}
.vchain .step span {{ font-size: 12px; color: #6B7080; }}
.vchain .step.mine {{ border-color: #2D5F9A; background: {ICE}; }}
.vchain .step.value {{ border-color: {RUST}; background: {PEACH}; }}
.vchain .arrow {{ color: {RUST}; font-size: 20px; font-weight: bold; }}
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
KIND_ORDER = {"tournament": 0, "ranked": 1, "public": 2, "mock": 3}


def datasets() -> dict[str, dict]:
    """Every dataset folder with processed matches: data/sample/* (baked into the image) and local
    data/processed/* (wins on a name clash). Info from dataset.json; ordered tournaments (newest first),
    ranked/public, mock."""
    out: dict[str, dict] = {}
    for base in (path("sample"), path("processed")):
        if not base.exists():
            continue
        for d in sorted(base.iterdir()):
            if not d.is_dir() or not any((m / "meta.json").exists() for m in d.iterdir() if m.is_dir()):
                continue
            info: dict = {}
            for f in (path("sample") / d.name / "dataset.json", path("raw") / d.name / "dataset.json",
                      d / "dataset.json"):  # baked info first, local files override
                if f.exists():
                    info |= json.loads(f.read_text(encoding="utf8"))
            if not (d / str(info.get("showcase")) / "meta.json").exists():
                info["showcase"] = next(m.name for m in sorted(d.iterdir()) if (m / "meta.json").exists())
            kind = info.get("kind") or ("mock" if d.name == "mock" else "public")
            out[d.name] = dict(name=d.name, folder=str(d), label=info.get("label", d.name), kind=kind,
                               show_names=bool(info.get("show_names")), showcase=info.get("showcase"),
                               created=info.get("created", ""))
    return dict(sorted(out.items(), key=lambda kv: (KIND_ORDER.get(kv[1]["kind"], 9),
                                                    "".join(chr(255 - ord(c)) for c in kv[1]["created"]))))


@st.cache_data(show_spinner=False)
def match_table(folder: str) -> pd.DataFrame:
    rows = []
    for m in sorted(Path(folder).iterdir()):
        if (m / "meta.json").exists():
            rows.append(json.loads((m / "meta.json").read_text(encoding="utf8")))
    df = pd.DataFrame(rows)
    return df.sort_values("createdAt").reset_index(drop=True) if len(df) else df


@st.cache_data(show_spinner=False, max_entries=16)
def load_labels(folder: str, match_id: str) -> dict[str, str]:
    """id → display name for teams (tag, e.g. MiTH) and players (name without the tag), from players.parquet.
    Empty when the dataset keeps no names (then ids are shown)."""
    f = Path(folder) / match_id / "players.parquet"
    if not f.exists():
        return {}
    pl = pd.read_parquet(f)
    out = {r.player: r.name for r in pl.itertuples() if r.name and r.name != r.player}
    out |= {r.team: r.team_name for r in pl.drop_duplicates("team").itertuples() if r.team_name and r.team_name != r.team}
    return out


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


# ---------------- sidebar ----------------
def _reset_params() -> None:
    for k, v in default_params().items():
        st.session_state[f"p_{k}"] = v
    st.session_state["_params"] = default_params()


def _remembered(key: str, options: list, default) -> dict:
    """Keep a sidebar choice across pages: Streamlit drops/rebuilds widget state on page switch, so the value lives
    in a shadow key (updated by on_change) and is restored before the widget is drawn. Returns widget kwargs."""
    shadow = f"_{key}"
    cur = st.session_state.get(shadow)
    if cur not in options:
        cur = default if default in options else options[0]
    st.session_state[shadow] = cur
    st.session_state[key] = cur

    def save() -> None:
        st.session_state[shadow] = st.session_state[key]

    return dict(key=key, on_change=save)


def match_label(r, i: int, showcase: str | None) -> str:
    d = int(r["duration"]) if pd.notna(r.get("duration")) else 0
    when = str(r.get("createdAt", ""))[5:16].replace("T", " ")
    when = f"{when[3:5]}/{when[0:2]} {when[6:]}" if len(when) >= 11 else when
    return f"Trận {i + 1} · {when} · {d // 60}:{d % 60:02d}" + (" ★" if r["match_id"] == showcase else "")


def sidebar(match_picker: bool = True, params: bool = True) -> dict:
    """Shared sidebar: dataset + match pickers, names toggle, algorithm parameters.
    Returns dict(source, dataset, folder, matches, match_id, meta, labels, params)."""
    ds_all = datasets()
    st.sidebar.markdown("### 🎯 Gathering · PUBG")
    if not ds_all:
        st.sidebar.error("Không có dữ liệu. Chạy `scripts/build_sample.py` hoặc pipeline (README).")
        st.stop()
    names = list(ds_all)
    default_ds = (load_config().get("app") or {}).get("default_dataset")
    name = st.sidebar.selectbox("Bộ dữ liệu", names, **_remembered("dataset", names, default_ds), format_func=lambda n: (
        f"{ds_all[n]['label']} · {len(match_table(ds_all[n]['folder']))} trận"))
    ds = ds_all[name]
    real = ds["kind"] != "mock"
    st.sidebar.markdown(f'<span class="badge {"real" if real else "mock"}">{"REAL" if real else "MOCK"} · '
                        f'{ds["label"]}</span>', unsafe_allow_html=True)
    mt = match_table(ds["folder"])
    out = dict(source=name, dataset=ds, folder=ds["folder"], matches=mt, match_id=None, params=default_params(),
               meta=None, labels={})
    if len(mt):
        ids = list(mt["match_id"])
        lab = {r["match_id"]: match_label(r, i, ds["showcase"]) for i, r in mt.iterrows()}
        key = f"match_{name}"
        kw = _remembered(key, ids, ds["showcase"])
        if match_picker and len(ids) > 1:
            mid = st.sidebar.selectbox("Trận (★ = trận mẫu)", ids, **kw, format_func=lambda m: lab[m])
        else:
            mid = st.session_state[key]
            st.sidebar.caption(lab[mid])
        out["match_id"] = mid
        out["meta"] = mt.set_index("match_id").loc[mid].to_dict()
        m = out["meta"]
        st.sidebar.caption(f"Erangel · {m.get('gameMode')} · {m.get('n_teams')} đội · {m.get('n_players')} người")
        if ds["show_names"]:
            if st.sidebar.toggle("Hiện tên đội / người chơi", **_remembered("show_names", [True, False], True)):
                out["labels"] = load_labels(ds["folder"], mid)
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
    return f"[{'REAL' if ctx['dataset']['kind'] != 'mock' else 'MOCK'} · {ctx['dataset']['label']}]"


def label_fn(ctx: dict):
    """id → display label (team tag / player name when names are on, else the id)."""
    labels = ctx.get("labels") or {}
    return lambda x: labels.get(x, x)


def params_key(p: dict) -> tuple:
    return tuple(sorted(p.items()))
