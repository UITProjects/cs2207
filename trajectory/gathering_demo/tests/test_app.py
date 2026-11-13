"""Smoke test: every page renders without exceptions on the available data (processed or sample)."""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app"
VIEWS = ["views/match.py", "views/algorithm.py"]  # in the menu (app/Home.py router)
ARCHIVE = sorted(f"archive/{p.name}" for p in (APP / "archive").glob("*.py"))  # kept, not in the menu


def routed(view: str) -> AppTest:
    at = AppTest.from_file(str(APP / "Home.py"), default_timeout=120).run()
    assert not at.exception, [e.value for e in at.exception]
    return at.switch_page(view).run()


@pytest.mark.parametrize("view", VIEWS)
def test_view_runs(view):
    at = routed(view)
    assert not at.exception, [e.value for e in at.exception]


@pytest.mark.parametrize("page", ARCHIVE)
def test_archive_page_runs(page):
    at = AppTest.from_file(str(APP / page), default_timeout=120).run()
    assert not at.exception, [e.value for e in at.exception]


def test_match_page_focus_and_follow():
    at = routed("views/match.py")
    ms = at.multiselect[0]
    assert 1 <= len(ms.value) <= 4
    first = ms.value[0]
    ms.set_value([first]).run()
    assert not at.exception
    at.selectbox(key=next(s.key for s in at.selectbox if s.key and s.key.startswith("follow_"))).set_value(first).run()
    assert not at.exception, [e.value for e in at.exception]


def test_algorithm_param_change():
    at = routed("views/algorithm.py")
    at.slider(key="p_m_c").set_value(5).run()
    at.slider(key="p_k_c").set_value(3).run()
    assert not at.exception
    at.button[0].click().run()  # reset to defaults
    assert not at.exception and at.slider(key="p_m_c").value == 8


def test_algorithm_2d_and_back():
    at = routed("views/algorithm.py")
    at.get("button_group")[0].set_value("🗺️ 2D").run()
    assert not at.exception, [e.value for e in at.exception]
    at.get("button_group")[0].set_value("🧊 3D x–y–t").run()  # re-fetch: the widget tree changed
    assert not at.exception, [e.value for e in at.exception]


def test_match_cube_toggles_and_encounter_2d():
    at = routed("views/match.py")
    at.toggle(key="cube_others").set_value(False).run()
    at.toggle(key="cube_gath").set_value(False).run()
    assert not at.exception, [e.value for e in at.exception]
    at.get("button_group")[0].set_value("2D").run()
    assert not at.exception, [e.value for e in at.exception]
