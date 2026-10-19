"""Work orders: an alert dispatched from the dashboard reaches an external service and is stored."""
import json
import shutil
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from pdm import db, work_orders as wo

APP = str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py")


class Receiver:
    """A local HTTP service that records what it is sent and answers with the given status codes in turn."""

    def __init__(self, statuses=(201,)):
        self.requests, self.statuses = [], list(statuses)
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                receiver.requests.append((dict(self.headers), json.loads(body)))
                status = receiver.statuses.pop(0) if len(receiver.statuses) > 1 else receiver.statuses[0]
                self.send_response(status)
                self.end_headers()
                self.wfile.write(b'{"id": "CMMS-1"}' if status < 300 else b"service unavailable")

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/work-orders"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def receiver():
    r = Receiver()
    yield r
    r.close()


@pytest.fixture
def db_copy(built_db, tmp_path):
    path = tmp_path / "maintenance.db"
    shutil.copy(built_db, path)
    return path


def _critical_alert(path):
    alerts = db.get_alerts("MTR_01", path)
    return alerts[alerts["status_level"] == "Critical"].iloc[0]


def test_dispatch_sends_the_alert_and_stores_the_work_order(db_copy, receiver):
    alert = _critical_alert(db_copy)
    order = wo.dispatch(alert["alert_id"], env={"PDM_WORK_ORDER_URL": receiver.url, "PDM_WORK_ORDER_TOKEN": "s3cret"},
                        db_path=db_copy)
    assert order["delivery"] == "sent" and order["response_code"] == 201
    headers, payload = receiver.requests[0]
    assert headers["Authorization"] == "Bearer s3cret"
    assert headers["Idempotency-Key"] == payload["work_order_id"] == order["work_order_id"]
    assert payload["schema"] == "pdm.work_order.v1" and payload["priority"] == "high"
    assert payload["asset"]["asset_id"] == "MTR_01"
    assert payload["alert"]["alert_id"] == alert["alert_id"]
    assert payload["alert"]["detected_issue"] == alert["detected_issue"]
    assert payload["condition"]["status"] == "Critical" and payload["condition"]["health_score"] is not None
    stored = wo.get(alert["alert_id"], db_copy)
    assert stored["delivery"] == "sent" and json.loads(stored["payload"]) == payload


def test_a_failed_delivery_is_kept_and_can_be_sent_again_under_the_same_id(db_copy):
    receiver = Receiver(statuses=(503, 200))
    try:
        alert_id = _critical_alert(db_copy)["alert_id"]
        env = {"PDM_WORK_ORDER_URL": receiver.url}
        first = wo.dispatch(alert_id, env=env, db_path=db_copy)
        assert first["delivery"] == "failed" and first["response_code"] == 503
        assert "service unavailable" in first["response"]
        second = wo.dispatch(alert_id, env=env, db_path=db_copy)
        assert second["delivery"] == "sent"
        assert second["work_order_id"] == first["work_order_id"] and second["created_at"] == first["created_at"]
        assert len(db.get_work_orders("MTR_01", db_copy)) == 1
    finally:
        receiver.close()


def test_an_unreachable_service_is_a_failed_delivery_not_a_crash(db_copy):
    alert_id = _critical_alert(db_copy)["alert_id"]
    order = wo.dispatch(alert_id, cfg=wo.WebhookConfig("http://127.0.0.1:9/nothing", timeout=2), db_path=db_copy)
    assert order["delivery"] == "failed" and order["response_code"] is None and order["response"]
    bad = wo.dispatch(alert_id, cfg=wo.WebhookConfig("file:///etc/passwd"), db_path=db_copy)
    assert bad["delivery"] == "failed" and "http" in bad["response"]


def test_without_a_service_the_order_is_stored_but_not_sent(db_copy):
    order = wo.dispatch(_critical_alert(db_copy)["alert_id"], env={}, db_path=db_copy)
    assert order["delivery"] == "not_configured" and order["target"] is None
    assert wo.WebhookConfig.from_env({"PDM_WORK_ORDER_URL": "  "}) is None


def test_a_database_built_before_work_orders_existed_gets_the_table(db_copy):
    with sqlite3.connect(db_copy) as conn:
        conn.execute("DROP TABLE work_orders")
    assert db.get_work_orders(db_path=db_copy).empty
    wo.dispatch(_critical_alert(db_copy)["alert_id"], env={}, db_path=db_copy)
    db.delete_asset("MTR_01", db_copy)
    assert db.get_work_orders(db_path=db_copy).empty


def test_the_dashboard_button_dispatches_the_work_order(db_copy, receiver, monkeypatch):
    monkeypatch.setattr(db, "DB_NAME", db_copy)
    monkeypatch.setenv("PDM_WORK_ORDER_URL", receiver.url)
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.session_state["selected_asset"] = "MTR_01"
    at.radio(key="view").set_value("Asset detail").run()
    newest = db.get_alerts("MTR_01", db_copy).iloc[0]
    at.button(key=f"btn_MTR_01_{newest['alert_id']}").click().run()
    assert not at.exception
    assert [p["alert"]["alert_id"] for _, p in receiver.requests] == [newest["alert_id"]]
    assert any("sent to" in s.value for s in at.success)
    at.run()                                                     # the next rerun shows the stored order
    assert f"btn_MTR_01_{newest['alert_id']}" not in [b.key for b in at.button]      # sent: no second dispatch
    assert any(f"WO-MTR_01-{newest['alert_id']}" in s.value for s in at.success) and len(receiver.requests) == 1
