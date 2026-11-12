"""Smoke test: every page renders without exceptions on the available data (processed or sample)."""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app"
PAGES = ["Home.py"] + sorted(f"pages/{p.name}" for p in (APP / "pages").glob("*.py"))


@pytest.mark.parametrize("page", PAGES)
def test_page_runs(page):
    at = AppTest.from_file(str(APP / page), default_timeout=120).run()
    assert not at.exception, [e.value for e in at.exception]


def test_step_by_step_param_change():
    at = AppTest.from_file(str(APP / "pages/2_Step_by_step.py"), default_timeout=120).run()
    at.slider(key="p_m_c").set_value(5).run()
    at.slider(key="p_k_c").set_value(3).run()
    assert not at.exception
    at.button[0].click().run()  # reset to defaults
    assert not at.exception and at.slider(key="p_m_c").value == 8
