"""Smoke test: every page renders without exceptions on the available data (processed or sample)."""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app"
VIEWS = ["views/algorithm.py", "views/match.py"]  # menu order (app/Home.py router): algorithm → result


def routed(view: str) -> AppTest:
    at = AppTest.from_file(str(APP / "Home.py"), default_timeout=120).run()
    assert not at.exception, [e.value for e in at.exception]
    return at.switch_page(view).run()


@pytest.mark.parametrize("view", VIEWS)
def test_view_runs(view):
    at = routed(view)
    assert not at.exception, [e.value for e in at.exception]


def test_algorithm_is_default_page():
    at = AppTest.from_file(str(APP / "Home.py"), default_timeout=120).run()
    assert not at.exception
    assert any("Thuật toán" in t.value for t in at.title)


def _bg(at, key):
    return next(b for b in at.get("button_group") if b.key == key)


def test_match_page_focus_and_follow():
    at = routed("views/match.py")
    ms = at.multiselect[0]
    assert 1 <= len(ms.value) <= 4
    first = ms.value[0]
    ms.set_value([first]).run()
    assert not at.exception
    _bg(at, "move_view").set_value("Replay").run()
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
    _bg(at, "move_view").set_value("3D x–y–t").run()
    at.toggle(key="cube_others").set_value(False).run()
    at.toggle(key="cube_gath").set_value(False).run()
    assert not at.exception, [e.value for e in at.exception]
    _bg(at, "encm_enc").set_value("2D").run()
    assert not at.exception, [e.value for e in at.exception]


def test_result_page_is_trajectory_only():
    at = routed("views/match.py")
    text = " ".join([m.value for m in at.markdown] + [c.value for c in at.caption])
    assert "gathering" in text
    for banned in ("bị loại", "hạng", "kết luận cho HLV", "VOD"):
        assert banned not in text, banned
    assert len(at.tabs) == 2


def test_algorithm_team_filter_and_per_player():
    at = routed("views/algorithm.py")
    ms = at.multiselect[0]
    assert len(ms.value) >= 2
    ms.set_value(ms.value[:1]).run()
    assert not at.exception, [e.value for e in at.exception]
    by = next(b for b in at.get("button_group") if b.key == "by_raw")
    by.set_value("Từng người").run()
    assert not at.exception, [e.value for e in at.exception]
