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


def test_algorithm_team_filter_per_player():
    at = routed("views/algorithm.py")
    ms = at.multiselect[0]
    assert len(ms.value) >= 2
    ms.set_value(ms.value[:1]).run()
    assert not at.exception, [e.value for e in at.exception]
    assert not any(b.key and b.key.startswith("by_") for b in at.get("button_group"))  # always per player
    at.toggle(key="conn_raw").set_value(False).run()
    assert not at.exception, [e.value for e in at.exception]


def test_dataset_picker_and_names():
    at = routed("views/match.py")
    ds = at.sidebar.selectbox(key="dataset")
    assert len(ds.options) >= 4 and ds.value == "as-pgs12gf"  # 3 tournaments + mock, PGS opens first
    assert any("PGS 12 Grand Final" in o for o in ds.options)
    focus = at.multiselect[0]
    assert any(o in ("MiTH", "FLC", "NAVI", "T1", "4AM", "GEN", "TWIS") for o in focus.options), focus.options
    at.sidebar.toggle(key="show_names").set_value(False).run()
    assert not at.exception, [e.value for e in at.exception]
    assert all(o.startswith("T") and o[1:].isdigit() for o in at.multiselect[0].options)  # ids when names off
    for name in ("sea-pacp26", "mock"):
        at.sidebar.selectbox(key="dataset").set_value(name).run()
        assert not at.exception, [e.value for e in at.exception]


def test_match_picker_switches_match():
    at = routed("views/algorithm.py")
    sb = at.sidebar.selectbox(key="match_as-pgs12gf")
    assert len(sb.options) == 5
    for mid in sb.options[:2]:
        at.sidebar.selectbox(key="match_as-pgs12gf").set_value(mid).run()
        assert not at.exception, [e.value for e in at.exception]
