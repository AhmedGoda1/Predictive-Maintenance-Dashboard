"""Login: admins see the full dashboard, the maintenance team only the open work orders."""
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import auth
from pdm import db, work_orders as wo

APP = str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py")
USERS = {"boss": {"password": auth.hash_password("admin-pw", 1000), "role": "admin"},
         "tech": {"password": "tech-pw", "role": "maintenance"},
         "odd": {"password": "x", "role": "visitor"}}


def test_password_hashes():
    stored = auth.hash_password("s3cret", 1000)
    assert stored.startswith("pbkdf2_sha256$1000$") and "s3cret" not in stored
    assert auth.check_password("s3cret", stored) and not auth.check_password("S3cret", stored)
    assert auth.check_password("plain", "plain") and not auth.check_password("plain", "other")
    assert not auth.check_password("", None) and not auth.check_password("x", "pbkdf2_sha256$nan$s$d")


@pytest.mark.parametrize("name, password, role", [
    ("boss", "admin-pw", "admin"), (" tech ", "tech-pw", "maintenance"),
    ("boss", "tech-pw", None), ("nobody", "admin-pw", None), ("odd", "x", None), ("", "", None)])
def test_authenticate(name, password, role):
    assert auth.authenticate(name, password, USERS) == role


@pytest.fixture
def db_copy(built_db, tmp_path, monkeypatch):
    path = tmp_path / "maintenance.db"
    shutil.copy(built_db, path)
    monkeypatch.setattr(db, "DB_NAME", path)
    monkeypatch.setenv("PDM_REFRESH_SECONDS", "0")
    monkeypatch.delenv("PDM_MQTT_HOST", raising=False)
    return path


def _app():
    at = AppTest.from_file(APP, default_timeout=120)
    at.secrets["users"] = USERS
    return at.run()


def _login(at, name, password):
    at.text_input(key="login_user").input(name)
    at.text_input(key="login_password").input(password)
    at.button[0].click().run()          # the form's submit button
    return at


def _orders(path):
    """Three work orders on MTR_01's alerts: one open, one in progress, one completed."""
    alerts = db.get_alerts("MTR_01", path).iloc[:3]
    ids = [wo.dispatch(a, env={}, db_path=path)["work_order_id"] for a in alerts["alert_id"]]
    wo.confirm(ids[1], {"status": "in_progress"}, path)
    wo.confirm(ids[2], {"status": "completed"}, path)
    return ids


def test_with_accounts_configured_nothing_shows_before_login(db_copy):
    at = _app()
    assert not at.exception
    assert [t.value for t in at.title] == ["🛠️ Maintenance Portal"] and not at.metric
    _login(at, "boss", "wrong")
    assert any("Wrong username or password" in e.value for e in at.error) and not at.metric


def test_admin_sees_the_full_dashboard(db_copy):
    at = _login(_app(), "boss", "admin-pw")
    assert not at.exception
    assert {m.label: m.value for m in at.metric}["Assets monitored"] == "21"
    assert at.radio(key="view") is not None and at.button(key="feed_start") is not None
    assert any("Logged in as **boss** (admin)" in c.value for c in at.sidebar.caption)
    at.button(key="logout").click().run()
    assert not at.metric and at.text_input(key="login_user") is not None


def test_maintenance_sees_only_open_work_orders_and_no_fleet_or_feed(db_copy):
    ids = _orders(db_copy)
    at = _login(_app(), "tech", "tech-pw")
    assert not at.exception
    assert not at.metric and any(x.value.startswith("**2 open**") for x in at.markdown)
    text = " ".join(x.value for x in at.markdown) + " ".join(x.value for x in at.caption)
    assert ids[0] in text and ids[1] in text and ids[2] not in text
    assert "feed_start" not in [b.key for b in at.button] and not [r for r in at.radio if r.key == "view"]


def test_a_technician_confirms_progress_from_the_page(db_copy):
    ids = _orders(db_copy)
    at = _login(_app(), "tech", "tech-pw")
    at.button(key=f"wo_in_progress_{ids[0]}").click().run()
    assert not at.exception and db.get_work_order(ids[0], db_copy)["status"] == "in_progress"
    at.text_input(key=f"note_{ids[1]}").input("bearing replaced")
    at.button(key=f"wo_completed_{ids[1]}").click().run()
    assert not at.exception
    done = db.get_work_order(ids[1], db_copy)
    assert done["status"] == "completed" and done["status_note"] == "tech: bearing replaced"
    assert any(x.value.startswith("**1 open**") for x in at.markdown)


def test_no_accounts_means_no_login_and_the_full_dashboard(db_copy):
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception and {m.label: m.value for m in at.metric}["Assets monitored"] == "21"
    assert any("No login is configured" in c.value for c in at.sidebar.caption)
