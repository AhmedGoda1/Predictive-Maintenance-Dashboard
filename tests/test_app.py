from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import utils
from pdm import db

APP = str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py")


@pytest.fixture
def app(built_db, monkeypatch):
    monkeypatch.setattr(db, "DB_NAME", built_db)
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    return at


def _metrics(at):
    return {m.label: m.value for m in at.metric}


def test_fleet_view_shows_status_counts(app):
    assert not app.exception
    m = _metrics(app)
    assert m["Assets monitored"] == "21"
    assert (m["⚫ Failed"], m["🔴 Critical"], m["🟡 Warning"], m["🟢 Healthy"]) == ("1", "8", "3", "9")


def test_fleet_filters(app):
    app.selectbox(key="fleet_type").set_value("turbofan_engine").run()
    assert not app.exception and _metrics(app)["Assets monitored"] == "20"
    app.slider(key="fleet_pct").set_value(0).run()                       # start of every asset's life
    m = _metrics(app)
    assert m["🟢 Healthy"] == "20" and m["🔴 Critical"] == "0"


def test_detail_opens_on_the_asset_that_needs_attention_most(app):
    app.radio(key="view").set_value("Asset detail").run()
    assert not app.exception and app.session_state["selected_asset"] == "MTR_01"     # the only Failed asset


def test_asset_views_render_for_both_types(app):
    app.radio(key="view").set_value("Asset detail").run()
    for asset in ["FD001-test-021", "MTR_01"]:
        app.session_state["selected_asset"] = asset
        app.run()
        assert not app.exception, asset
        m = _metrics(app)
        assert "Estimated RUL" in m and "Health index" in m
    assert m["Status"] == "⚫ Failed"                                     # the motor at the end of its run


def test_engine_detail_reports_interval_and_model_quality(app):
    app.session_state["selected_asset"] = "FD001-test-021"
    app.radio(key="view").set_value("Asset detail").run()
    m = _metrics(app)
    assert m["Estimated RUL"] == "59 cycles" and m["Actual remaining life"] == "57 cycles"
    assert m["Interval coverage (nominal 80%)"] == "80%"
    assert any("80% range" in c.value for c in app.caption)


def test_replay_position_moves_the_asset(app):
    app.session_state["selected_asset"] = "FD001-test-021"
    app.radio(key="view").set_value("Asset detail").run()
    app.slider(key="pos_FD001-test-021").set_value(40).run()
    assert not app.exception and _metrics(app)["Age"] == "40 cycles"


def test_charts_build_for_every_type_and_view(built_db, monkeypatch):
    monkeypatch.setattr(db, "DB_NAME", built_db)
    import data_source as ds
    fleet = ds.load_fleet()
    snap = ds.snapshot(fleet, 1.0)
    assert len(utils.plot_fleet_health(snap).data) == 4                   # one trace per status present
    assert len(utils.plot_fleet_rul(snap, "turbofan_engine").data) >= 3
    for asset in ["FD001-test-021", "MTR_01"]:
        a = ds.load_asset(asset)
        xr = [a.data["age_disp"].min(), a.data["age_disp"].max()]
        utils.plot_health_timeline(a.data, a.type, xr)
        utils.plot_rul(a.data, a.type, xr)
        utils.plot_health_gauge(50, "Warning", a.type)
        for ch in a.type.sensor_names:
            if a.data[ch].notna().any():
                utils.plot_sensor(a.data, a.type, ch, xr)


def test_app_survives_a_deployment_that_updates_modules_under_a_running_process(tmp_path):
    """A running Streamlit process keeps old `pdm` modules in memory while dashboard/ is hot-reloaded.

    Seen in production as: AttributeError: module 'pdm.db' has no attribute 'is_current'.
    Runs in its own process because it replaces modules in sys.modules.
    """
    import os
    import subprocess
    import sys
    script = f"""
import sys
import streamlit as st
from streamlit.testing.v1 import AppTest

at = AppTest.from_file({APP!r}, default_timeout=180).run()
assert not at.exception, [e.value for e in at.exception]

# the running process still holds an old pdm.db; the source files on disk have since changed
del sys.modules["pdm.db"].is_current
sys._dashboard_code_signature = "an older deployment"
st.cache_data.clear()                                   # a new visitor
at.run()
assert not at.exception, [e.value for e in at.exception]
assert {{m.label: m.value for m in at.metric}}["Assets monitored"] == "21"
print("OK")
"""
    env = {**os.environ, "MAINTENANCE_DB": str(tmp_path / "maintenance.db")}
    result = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0 and "OK" in result.stdout, result.stderr[-2000:]


# ================================================================ live data in the dashboard
@pytest.fixture
def live_app(built_db, monkeypatch):
    """The app on a copy of the demo database, with caches cleared and any feed stopped afterwards."""
    import shutil
    import streamlit as st
    import tempfile
    path = Path(tempfile.mkdtemp()) / "maintenance.db"
    shutil.copy(built_db, path)
    monkeypatch.setattr(db, "DB_NAME", path)
    monkeypatch.delenv("PDM_MQTT_HOST", raising=False)
    monkeypatch.setenv("PDM_REFRESH_SECONDS", "0")      # the auto-refresh loop never ends; the tests rerun by hand
    st.cache_resource.clear()
    st.cache_data.clear()
    yield path
    import live_feed
    live_feed.stop_all()
    st.cache_resource.clear()


def _wait_until(at, condition, timeout=40):
    import time
    end = time.time() + timeout
    while time.time() < end:
        at.run()
        if condition():
            return True
        time.sleep(0.5)
    return False


def test_without_a_broker_the_panel_says_so_and_the_demo_feed_still_works(live_app):
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception
    assert any("does not run its own MQTT subscriber" in c.value for c in at.sidebar.caption)
    at.slider(key="feed_engines").set_value(1)
    at.sidebar.select_slider(key="feed_speed").set_value(0.25)
    at.button(key="feed_start").click().run()
    assert _wait_until(at, lambda: _metrics(at).get("Assets monitored") == "22")
    assert not at.exception
    at.button(key="feed_stop").click().run()


def test_with_a_broker_devices_reach_the_dashboard_through_mqtt(live_app, mqtt_broker, monkeypatch):
    """device -> broker -> the app's own ingestion subscriber -> database -> fleet view."""
    import time
    from pdm import mqtt_ingest, simulator
    monkeypatch.setenv("PDM_MQTT_HOST", mqtt_broker.host)
    monkeypatch.setenv("PDM_MQTT_PORT", str(mqtt_broker.port))
    monkeypatch.setenv("PDM_MQTT_CLIENT_ID", f"pdm-dash-test-{time.time_ns()}")
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception
    assert _wait_until(at, lambda: any("connected to" in c.value and "🟢" in c.value for c in at.sidebar.caption), timeout=20)

    # an external device (here: the simulator, as scripts/simulate.py would) publishes to the broker
    cfg = mqtt_ingest.MqttConfig(mqtt_broker.host, mqtt_broker.port)
    feeds = simulator.build_feeds(1)
    simulator.LiveFeed(feeds, simulator.MqttSink(cfg), interval_s=0, step=60).run()
    assert _wait_until(at, lambda: _metrics(at).get("Assets monitored") == "22"), "the live engine never appeared"
    at.radio(key="view").set_value("Asset detail")
    at.session_state["selected_asset"] = feeds[0].asset_id
    assert _wait_until(at, lambda: "Status" in _metrics(at)), "the live engine was never scored"   # first it is 'learning'
    assert not at.exception and _metrics(at)["Status"] in ("🟢 Healthy", "🟡 Warning", "🔴 Critical")


def test_an_asset_still_learning_its_baseline_is_shown_not_hidden(live_app):
    """A live asset with a few readings has no health scores yet: it must appear in the fleet and open cleanly."""
    from pdm import ingest
    from test_ingest import engine_rows
    ingest.register_asset("LIVE-NEW", "turbofan_engine", "Brand new engine", source="NASA C-MAPSS FD001", metadata={"live": True})
    rows, _ = engine_rows(n=7)
    ingest.ingest_readings("LIVE-NEW", rows)
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception and _metrics(at)["Assets monitored"] == "22"
    assert any("still learning" in c.value for c in at.caption)
    at.session_state["selected_asset"] = "LIVE-NEW"
    at.radio(key="view").set_value("Asset detail").run()
    assert not at.exception
    assert any("Learning the healthy baseline: 7 of 20" in i.value for i in at.info)


def test_a_new_subscriber_replaces_the_old_one_instead_of_fighting_it_for_the_session(mqtt_broker, monkeypatch):
    """After a code update the app starts a new subscriber; the old one must stop (same client id => session tug of war)."""
    import time
    import live_feed
    monkeypatch.setenv("PDM_MQTT_HOST", mqtt_broker.host)
    monkeypatch.setenv("PDM_MQTT_PORT", str(mqtt_broker.port))
    monkeypatch.setenv("PDM_MQTT_CLIENT_ID", f"pdm-replace-{time.time_ns()}")
    monkeypatch.setattr(db, "DB_NAME", Path(__import__("tempfile").mkdtemp()) / "x.db")
    try:
        first = live_feed.start_ingestor()
        second = live_feed.start_ingestor()
        assert first is not second and len(live_feed._ingestors) == 1
        assert not first.connected.is_set() and not first._worker.is_alive()     # fully stopped, not just detached
    finally:
        live_feed.stop_all()
