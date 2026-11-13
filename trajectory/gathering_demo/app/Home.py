"""Entry point: `streamlit run app/Home.py`. Two pages; recap/multi-match pages live in app/archive/."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

VIEWS = Path(__file__).resolve().parent / "views"

PAGES = [
    st.Page(VIEWS / "match.py", title="Trận đấu", icon="🎮", default=True),
    st.Page(VIEWS / "algorithm.py", title="Thuật toán", icon="🔬", url_path="thuat-toan"),
]

st.navigation(PAGES).run()
