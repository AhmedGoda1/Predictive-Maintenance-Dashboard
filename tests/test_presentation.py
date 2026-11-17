"""Presentation mode: branding, plain asset names and the guided tour."""
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
    at.query_params["customer"] = "Acme Aero"
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


def test_link_turns_it_on_with_the_customer_branding(app):
    assert not app.exception and app.toggle(key="present").value
    assert "Acme Aero" in _html(app) and "#c0392b" in _html(app)
    assert app.radio(key="view").options == presentation.VIEWS
    assert not any(e.label == "Live data (MQTT)" for e in app.expander)       # developer panels are hidden


def test_customer_name_can_be_changed_in_the_app(app):
    app.text_input(key="brand_customer").input("Globex Rail").run()
    assert not app.exception and "Globex Rail" in _html(app)
    assert app.query_params["customer"] == "Globex Rail"                   # the address bar is a shareable link


def test_plain_asset_names():
    import data_source as ds
    names = presentation.labels(ds.load_fleet())
    assert names["FD001-test-001"] == "Engine 01" and names["MTR_01"] == "Drive motor"


def test_guided_tour_walks_every_step(app):
    app.button(key="tour_start").click().run()
    assert app.session_state["tour_step"] == 0 and app.slider(key="fleet_pct").value == 15
    for i in range(1, len(presentation.TOUR)):
        app.button(key="tour_next").click().run()
        assert not app.exception, presentation.TOUR[i].title
        assert app.session_state["tour_step"] == i and app.session_state["view"] == presentation.TOUR[i].view
    assert any(t.value == "Next steps for Acme Aero" for t in app.title)
    app.button(key="tour_end").click().run()
    assert not app.exception and "tour_step" not in app.session_state


def test_turning_it_off_restores_the_normal_dashboard(app):
    app.toggle(key="present").set_value(False).run()
    assert not app.exception and app.radio(key="view").options == ["Fleet", "Asset detail"]
    assert "present" not in app.query_params


def test_switching_between_saved_customers(app):
    assert app.selectbox(key="profile_pick").options == ["Acme Aero", presentation.NEW_PROFILE]
    app.selectbox(key="profile_pick").set_value(presentation.NEW_PROFILE).run()
    assert app.text_input(key="brand_customer").value == ""
    app.text_input(key="brand_customer").input("Globex Rail").run()
    app.color_picker(key="brand_accent").pick("#117a65").run()
    app.text_input(key="noun_turbofan_engine").input("Locomotive").run()
    app.button(key="profile_save").click().run()
    assert not app.exception and app.selectbox(key="profile_pick").value == "Globex Rail"
    app.selectbox(key="profile_pick").set_value("Acme Aero").run()          # back to the first customer
    assert "Acme Aero" in _html(app) and "#c0392b" in _html(app)
    assert app.text_input(key="noun_turbofan_engine").value == "Engine"
    app.selectbox(key="profile_pick").set_value("Globex Rail").run()
    assert "Globex Rail" in _html(app) and "#117a65" in _html(app)
    assert app.text_input(key="noun_turbofan_engine").value == "Locomotive"



@pytest.fixture
def course_app(built_db, monkeypatch):
    monkeypatch.setattr(db, "DB_NAME", built_db)
    monkeypatch.setenv("PDM_REFRESH_SECONDS", "0")
    at = AppTest.from_file(APP, default_timeout=120)
    at.query_params["present"] = "1"
    at.query_params["audience"] = "course"
    at.query_params["team"] = "Joni, Ahmed"
    at.run()
    return at


def test_course_link_opens_the_course_presentation(course_app):
    app = course_app
    assert not app.exception and app.radio(key="brand_audience").value == "course"
    assert app.radio(key="view").options == presentation.COURSE_VIEWS
    page = _html(app)
    assert presentation.COURSE_DEFAULTS["customer"] in page and "Joni, Ahmed" in page


def test_course_tour_walks_every_step(course_app):
    app = course_app
    app.button(key="tour_start").click().run()
    assert app.session_state["view"] == "Problem" and any(t.value == "The problem" for t in app.title)
    for i in range(1, len(presentation.COURSE_TOUR)):
        app.button(key="tour_next").click().run()
        assert not app.exception, presentation.COURSE_TOUR[i].title
        assert app.session_state["view"] == presentation.COURSE_TOUR[i].view
        if presentation.COURSE_TOUR[i].view == "Results":
            assert any(m.label == "Average error (MAE)" for m in app.metric)
        if presentation.COURSE_TOUR[i].view == "Testing":
            assert any(m.label == "Automated tests (pytest)" and int(m.value) > 100 for m in app.metric)
    assert any(t.value == "Lessons learned" for t in app.title)
    assert presentation.DEFAULT_LESSONS["improve"].splitlines()[0] in " ".join(m.value for m in app.markdown)


def test_course_tour_follows_the_course_structure():
    views = [s.view for s in presentation.COURSE_TOUR]
    order = ["Problem", "Users", "Requirements", "Architecture", "Fleet", "Testing", "Lessons learned"]
    assert [views.index(v) for v in order] == sorted(views.index(v) for v in order)
    assert len(presentation.COURSE_TOUR) == 15


def test_switching_the_audience_swaps_the_default_wording(app):
    app.text_input(key="brand_customer").input(presentation.DEFAULTS["customer"]).run()
    app.button(key="tour_start").click().run()
    app.radio(key="brand_audience").set_value("course").run()
    assert not app.exception and "tour_step" not in app.session_state          # the tours differ
    assert app.text_input(key="brand_customer").value == presentation.COURSE_DEFAULTS["customer"]
    assert app.radio(key="view").options == presentation.COURSE_VIEWS
    assert app.query_params["audience"] == "course"
    app.radio(key="brand_audience").set_value("pitch").run()
    assert app.text_input(key="brand_customer").value == presentation.DEFAULTS["customer"]
    assert app.radio(key="view").options == presentation.VIEWS
