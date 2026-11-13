"""Entry point: `streamlit run app/Home.py`. Menu in presentation order (multi-match pages live in app/archive/)."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

VIEWS = Path(__file__).resolve().parent / "views"

PAGES = [
    st.Page(VIEWS / "intro.py", title="Giới thiệu", icon="🏠", default=True),
    st.Page(VIEWS / "match.py", title="Phân tích trận", icon="🎮", url_path="tran-dau"),
    st.Page(VIEWS / "algorithm.py", title="Thuật toán từng bước", icon="🔬", url_path="thuat-toan"),
]

st.navigation(PAGES).run()
