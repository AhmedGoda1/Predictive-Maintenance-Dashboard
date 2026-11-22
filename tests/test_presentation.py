"""Presentation mode (the course presentation): branding, plain asset names, profiles and the guided tour."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import presentation
from pdm import db

APP = str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py")


@pytest.fixture
def app(built_db, monkeypatch):
    monkeypatch.setattr(db, "DB_NAME", built_db)
    monkeypatch.setenv("PDM_REFRESH_SECONDS", "0")
    at = AppTest.from_file(APP, default_timeout=120)
    at.query_params["present"] = "1"
    at.query_params["customer"] = "Acme Project"
    at.query_params["team"] = "Joni, Ahmed"
    at.query_params["accent"] = "c0392b"
    at.run()
    return at


def _html(at) -> str:
    return " ".join(str(h.proto.body) for h in at.get("html"))


def test_off_by_default(built_db, monkeypatch):
    monkeypatch.setattr(db, "DB_NAME", built_db)
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception and not at.toggle(key="present").value
    assert at.radio(key="view").options == ["Fleet", "Asset detail"]
    assert "Acme" not in _html(at)


def test_link_turns_it_on_with_the_branding(app):
    assert not app.exception and app.toggle(key="present").value
    page = _html(app)
    assert "Acme Project" in page and "Joni, Ahmed" in page and "#c0392b" in page
    assert app.radio(key="view").options == presentation.VIEWS
    assert not any(e.label == "Live data (MQTT)" for e in app.expander)       # developer panels are hidden


def test_default_title_without_a_link(built_db, monkeypatch):
    monkeypatch.setattr(db, "DB_NAME", built_db)
    monkeypatch.setenv("PDM_REFRESH_SECONDS", "0")
    at = AppTest.from_file(APP, default_timeout=120)
    at.query_params["present"] = "1"
    at.run()
    assert not at.exception and presentation.DEFAULTS["customer"] in _html(at)


def test_only_the_course_presentation_is_offered(app):
    labels = [e.label for e in app.expander]
    assert not any("Before you present" in label for label in labels)
    assert not any(r.label == "Audience" for r in app.radio)
    assert "🎨 Customize this presentation" in labels


def test_title_can_be_changed_in_the_app(app):
    app.text_input(key="brand_customer").input("Globex Rail").run()
    assert not app.exception and "Globex Rail" in _html(app)
    assert app.query_params["customer"] == "Globex Rail"                   # the address bar is a shareable link


def test_plain_asset_names():
    import data_source as ds
    names = presentation.labels(ds.load_fleet())
    assert names["FD001-test-001"] == "Engine 01" and names["MTR_01"] == "Drive motor"


def test_guided_tour_walks_every_step(app):
    app.button(key="tour_start").click().run()
    assert app.session_state["view"] == "Problem" and any(t.value == "The problem" for t in app.title)
    for i in range(1, len(presentation.TOUR)):
        app.button(key="tour_next").click().run()
        assert not app.exception, presentation.TOUR[i].title
        assert app.session_state["tour_step"] == i and app.session_state["view"] == presentation.TOUR[i].view
        if presentation.TOUR[i].view == "Results":
            assert any(m.label == "Average error (MAE)" for m in app.metric)
        if presentation.TOUR[i].view == "Testing":
            assert any(m.label == "Automated tests (pytest)" and int(m.value) > 100 for m in app.metric)
    assert any(t.value == "Lessons learned" for t in app.title)
    assert presentation.DEFAULT_LESSONS["improve"].splitlines()[0] in " ".join(m.value for m in app.markdown)
    app.button(key="tour_end").click().run()
    assert not app.exception and "tour_step" not in app.session_state


def test_customizing_is_hidden_while_the_tour_runs(app):
    app.text_input(key="brand_customer").input("Globex Rail").run()
    app.button(key="tour_start").click().run()
    assert not app.exception
    assert not any(e.label.startswith("🎨") for e in app.expander)
    assert not app.get("selectbox") or all(s.key != "profile_pick" for s in app.selectbox)
    assert not any(b.key == "tour_start" for b in app.button)
    app.button(key="tour_next").click().run()
    assert "Globex Rail" in _html(app)                                      # the settings outlive the hidden panel
    app.button(key="tour_end").click().run()
    assert not app.exception and any(e.label.startswith("🎨") for e in app.expander)
    assert app.text_input(key="brand_customer").value == "Globex Rail"
    assert app.selectbox(key="profile_pick").value == "Acme Project"


def test_turning_it_off_restores_the_normal_dashboard(app):
    app.toggle(key="present").set_value(False).run()
    assert not app.exception and app.radio(key="view").options == ["Fleet", "Asset detail"]
    assert "present" not in app.query_params


def test_switching_between_saved_profiles(app):
    assert app.selectbox(key="profile_pick").options == ["Acme Project", presentation.NEW_PROFILE]
    app.selectbox(key="profile_pick").set_value(presentation.NEW_PROFILE).run()
    assert app.text_input(key="brand_customer").value == ""
    app.text_input(key="brand_customer").input("Globex Rail").run()
    app.color_picker(key="brand_accent").pick("#117a65").run()
    app.text_input(key="noun_turbofan_engine").input("Locomotive").run()
    app.button(key="profile_save").click().run()
    assert not app.exception and app.selectbox(key="profile_pick").value == "Globex Rail"
    app.selectbox(key="profile_pick").set_value("Acme Project").run()       # back to the first profile
    assert "Acme Project" in _html(app) and "#c0392b" in _html(app)
    assert app.text_input(key="noun_turbofan_engine").value == "Engine"
    app.selectbox(key="profile_pick").set_value("Globex Rail").run()
    assert "Globex Rail" in _html(app) and "#117a65" in _html(app)
    assert app.text_input(key="noun_turbofan_engine").value == "Locomotive"


def test_tour_follows_the_course_structure():
    views = [s.view for s in presentation.TOUR]
    order = ["Problem", "Users", "Requirements", "Architecture", "Fleet", "Testing", "Lessons learned"]
    assert [views.index(v) for v in order] == sorted(views.index(v) for v in order)
    assert len(presentation.TOUR) == 16
