"""Work orders: an alert dispatched from the dashboard reaches an external service and is stored."""
import json
import shutil
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import time
import urllib.error
import urllib.request

import pytest
from streamlit.testing.v1 import AppTest

from pdm import db, mqtt_ingest, work_order_callback, work_orders as wo

APP = str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py")


class Receiver:
    """A local HTTP service that records what it is sent and answers with the given status codes in turn."""

    def __init__(self, statuses=(201,), answer=b'{"id": "CMMS-1"}'):
        self.requests, self.statuses, self.answer = [], list(statuses), answer
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                receiver.requests.append((dict(self.headers), json.loads(body)))
                status = receiver.statuses.pop(0) if len(receiver.statuses) > 1 else receiver.statuses[0]
                self.send_response(status)
                self.end_headers()
                self.wfile.write(receiver.answer if status < 300 else b"service unavailable")

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


# ================================================================ confirmations from the service
@pytest.fixture
def order(db_copy):
    """A work order that was sent and not confirmed yet."""
    receiver = Receiver()
    try:
        return wo.dispatch(_critical_alert(db_copy)["alert_id"], env={"PDM_WORK_ORDER_URL": receiver.url},
                           db_path=db_copy)
    finally:
        receiver.close()


def test_the_payload_says_where_to_send_confirmations(db_copy, receiver):
    env = {"PDM_WORK_ORDER_URL": receiver.url, "PDM_MQTT_HOST": "broker",
           "PDM_WORK_ORDER_CALLBACK_URL": "https://pdm.example.com/"}
    order = wo.dispatch(_critical_alert(db_copy)["alert_id"], env=env, db_path=db_copy)
    reply_to = receiver.requests[0][1]["reply_to"]
    wid = order["work_order_id"]
    assert reply_to["mqtt_topic"] == f"pdm/v1/work_orders/{wid}/status"
    assert reply_to["http_url"] == f"https://pdm.example.com/work-orders/{wid}/status"
    assert reply_to["statuses"] == list(wo.STATUSES)
    assert wo.reply_to(wid, env={}) == {"statuses": list(wo.STATUSES), "mqtt_topic": None, "http_url": None}


def test_a_service_can_confirm_in_its_answer(db_copy):
    receiver = Receiver(answer=b'{"id": "CMMS-77", "status": "accepted"}')
    try:
        order = wo.dispatch(_critical_alert(db_copy)["alert_id"], env={"PDM_WORK_ORDER_URL": receiver.url},
                            db_path=db_copy)
    finally:
        receiver.close()
    assert order["status"] == "accepted" and order["external_id"] == "CMMS-77"


def test_an_answer_without_a_status_is_no_confirmation(order):
    assert order["delivery"] == "sent" and order["status"] is None


def test_confirmations_update_the_order_in_time_order(order, db_copy):
    wid = order["work_order_id"]
    wo.confirm(wid, {"status": "accepted", "external_id": "CMMS-1", "at": "2026-10-19T10:00:00Z"}, db_copy)
    wo.confirm(wid, {"status": "completed", "note": "bearing replaced", "at": "2026-10-19T12:00:00+02:00"}, db_copy)
    late = wo.confirm(wid, {"status": "in_progress", "at": "2026-10-19T09:30:00Z"}, db_copy)   # arrived out of order
    assert late["status"] == "completed" and late["external_id"] == "CMMS-1" and late["status_note"] == "bearing replaced"
    assert str(late["status_at"]) == "2026-10-19 10:00:00"                                    # stored in UTC


@pytest.mark.parametrize("message, fragment", [
    ({"status": "done"}, "status must be one of"),
    ({}, "status must be one of"),
    ("accepted", "JSON object"),
    ({"status": "accepted", "at": "yesterday-ish"}, "ISO 8601"),
    ({"status": "accepted", "note": "x" * 501}, "at most 500"),
])
def test_malformed_confirmations_are_refused(order, db_copy, message, fragment):
    with pytest.raises(ValueError, match=fragment):
        wo.confirm(order["work_order_id"], message, db_copy)


def test_a_confirmation_for_an_unknown_order_is_refused(db_copy):
    with pytest.raises(KeyError):
        wo.confirm("WO-nothing-1", {"status": "accepted"}, db_copy)


def test_mqtt_confirmations(order, db_copy):
    handler = mqtt_ingest.Handler(db_copy)
    wid = order["work_order_id"]
    assert wo.status_topic("+") in mqtt_ingest.SUBSCRIPTIONS
    assert handler.handle(wo.status_topic(wid), b'{"status": "in_progress", "external_id": "CMMS-9"}') == []
    assert db.get_work_order(wid, db_copy)["status"] == "in_progress"
    [(t, body, retain)] = handler.handle(wo.status_topic(wid), b'{"status": "nope"}')
    assert t == f"pdm/v1/work_orders/{wid}/rejected" and not retain and json.loads(body)["code"] == "invalid"
    [(_, body, _)] = handler.handle(wo.status_topic(wid), b"not json")
    assert json.loads(body)["error"] == "payload is not valid JSON"
    [(_, body, _)] = handler.handle(wo.status_topic("WO-x-1"), b'{"status": "accepted"}')
    assert json.loads(body)["code"] == "not_found"
    assert handler.handle("pdm/v1/work_orders/+/status", b'{"status": "accepted"}') == []


def test_mqtt_confirmation_through_a_broker(order, db_copy, mqtt_broker):
    cfg = mqtt_ingest.MqttConfig(mqtt_broker.host, mqtt_broker.port, client_id=f"test-wo-{time.time_ns()}")
    svc = mqtt_ingest.MqttIngestor(cfg, db_copy).start()
    pub = mqtt_ingest.new_client(cfg, client_id=f"test-service-{time.time_ns()}")
    try:
        assert svc.connected.is_set(), svc.status()
        pub.connect(cfg.host, cfg.port)
        pub.loop_start()
        pub.publish(wo.status_topic(order["work_order_id"]), json.dumps({"status": "accepted"}), qos=1).wait_for_publish(5)
        end = time.time() + 20
        while time.time() < end and db.get_work_order(order["work_order_id"], db_copy)["status"] != "accepted":
            time.sleep(0.1)
        assert db.get_work_order(order["work_order_id"], db_copy)["status"] == "accepted"
    finally:
        pub.loop_stop()
        pub.disconnect()
        svc.stop()


def _post(url, body, token="s3cret"):
    request = urllib.request.Request(url, data=body if isinstance(body, bytes) else json.dumps(body).encode(),
                                     method="POST", headers={"Content-Type": "application/json",
                                                             **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_http_confirmations(order, db_copy):
    server = work_order_callback.make_server("s3cret", "127.0.0.1", 0, db_copy)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    wid = order["work_order_id"]
    try:
        assert _post(f"{base}/work-orders/{wid}/status", {"status": "accepted"}, token=None)[0] == 401
        assert _post(f"{base}/work-orders/{wid}/status", {"status": "accepted"}, token="wrong")[0] == 401
        code, body = _post(f"{base}/work-orders/{wid}/status", {"status": "accepted", "external_id": 4711})
        assert code == 200 and body["status"] == "accepted" and body["external_id"] == "4711"
        assert db.get_work_order(wid, db_copy)["status"] == "accepted"
        assert _post(f"{base}/work-orders/{wid}/status", {"status": "done"})[0] == 400
        assert _post(f"{base}/work-orders/{wid}/status", b"{not json")[0] == 400
        assert _post(f"{base}/work-orders/WO-x-1/status", {"status": "accepted"})[0] == 404
        assert _post(f"{base}/elsewhere", {"status": "accepted"})[0] == 404
    finally:
        server.shutdown()
        server.server_close()
    with pytest.raises(ValueError):
        work_order_callback.make_server("", "127.0.0.1", 0)


def test_the_dashboard_shows_what_the_service_confirmed(order, db_copy, monkeypatch):
    wo.confirm(order["work_order_id"], {"status": "in_progress", "external_id": "CMMS-5", "note": "on site"}, db_copy)
    monkeypatch.setattr(db, "DB_NAME", db_copy)
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.session_state["selected_asset"] = "MTR_01"
    at.radio(key="view").set_value("Asset detail").run()
    assert not at.exception
    assert any("in progress" in i.value and "CMMS-5" in i.value and "on site" in i.value for i in at.info)


def test_without_a_service_the_dashboard_hands_the_order_to_the_maintenance_team(db_copy, monkeypatch):
    """No PDM_WORK_ORDER_URL is the normal setup: no warning, no resend button, the order is on the team's list."""
    monkeypatch.setattr(db, "DB_NAME", db_copy)
    monkeypatch.delenv("PDM_WORK_ORDER_URL", raising=False)
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.session_state["selected_asset"] = "MTR_01"
    at.radio(key="view").set_value("Asset detail").run()
    newest = db.get_alerts("MTR_01", db_copy).iloc[0]
    at.button(key=f"btn_MTR_01_{newest['alert_id']}").click().run()
    assert not at.exception and not [w for w in at.warning if "work order" in w.value.lower()]
    assert any("on the maintenance team's list" in s.value for s in at.success)
    at.run()
    assert f"btn_MTR_01_{newest['alert_id']}" not in [b.key for b in at.button]
    import data_source as ds
    assert list(ds.active_work_orders()["alert_id"]) == [newest["alert_id"]]
