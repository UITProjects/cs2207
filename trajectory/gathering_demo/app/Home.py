"""Entry point: `streamlit run app/Home.py`. Algorithm first, then the result."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

VIEWS = Path(__file__).resolve().parent / "views"

PAGES = [
    st.Page(VIEWS / "algorithm.py", title="Thuật toán", icon="🔬", default=True),
    st.Page(VIEWS / "match.py", title="Kết quả", icon="🎯", url_path="ket-qua"),
]

st.navigation(PAGES).run()
