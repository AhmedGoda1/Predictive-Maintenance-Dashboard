import json
import time

import paho.mqtt.client as mqtt
import pytest

from pdm import db, ingest, mqtt_ingest, simulator
from pdm.mqtt_ingest import Handler, MqttConfig, MqttIngestor, topic
from test_ingest import engine_rows


def wait_for(condition, timeout=30, every=0.1):
    """Polls until the condition holds; an error while polling (e.g. the asset is not registered yet) counts as not yet."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            if condition():
                return True
        except Exception:
            pass
        time.sleep(every)
    return False


def decode(outs):
    return {t.rsplit("/", 1)[1]: (json.loads(p), retain) for t, p, retain in outs}


# ================================================================ message handling, no broker needed
@pytest.fixture
def handler(live_db):
    return Handler(live_db)


def register(handler, asset_id="E1", **body):
    body = {"type_id": "turbofan_engine", "source": "NASA C-MAPSS FD001", **body}
    return handler.handle(topic(asset_id, "register"), json.dumps(body).encode())


@pytest.mark.parametrize("t, expected", [
    ("pdm/v1/assets/E1/readings", ("E1", "readings")),
    ("pdm/v1/assets/engine.7-a_b/register", ("engine.7-a_b", "register")),
    ("pdm/v1/assets/E1/failure", ("E1", "failure")),
    ("pdm/v1/assets/E1/state", None),                    # our own outbound topics are not inbound
    ("pdm/v1/assets/E1/rejected", None),
    ("pdm/v2/assets/E1/readings", None),
    ("other/v1/assets/E1/readings", None),
    ("pdm/v1/assets/E1/readings/extra", None),
    ("pdm/v1/assets/+/readings", None),                  # wildcards are never an asset id
    ("pdm/v1/assets/a b/readings", None),
    (f"pdm/v1/assets/{'x' * 65}/readings", None),
])
def test_topics(t, expected):
    assert Handler.parse_topic(t) == expected


def test_register_answers_with_the_asset_state(handler):
    state, retained = decode(register(handler))["state"]
    assert state["status"] == "Learning" and retained is True
    assert decode(register(handler))["state"][0]["status"] == "Learning"                # registering again is fine


def test_readings_in_every_accepted_shape(handler):
    register(handler)
    rows, _ = engine_rows(n=25)
    one = handler.handle(topic("E1", "readings"), json.dumps(rows[0]).encode())
    assert decode(one)["state"][0]["accepted"] == 1
    batch = handler.handle(topic("E1", "readings"), json.dumps({"readings": rows[1:11]}).encode())
    assert decode(batch)["state"][0]["accepted"] == 10
    bare = handler.handle(topic("E1", "readings"), json.dumps(rows[11:]).encode())
    state, retained = decode(bare)["state"]
    assert state["accepted"] == 14 and state["state"]["status"] == "Healthy" and retained is True
    assert "rejected" not in decode(bare)


def test_a_partly_refused_batch_reports_it_on_the_rejected_topic(handler):
    register(handler)
    rows, _ = engine_rows(n=3)
    bad = {"ts": "2030-01-01T00:00:00Z", "age": 9, "values": {"nonsense": 1}}
    out = decode(handler.handle(topic("E1", "readings"), json.dumps({"readings": [rows[0], bad, rows[1]]}).encode()))
    assert out["state"][0]["accepted"] == 2
    rejected, retained = out["rejected"]
    assert retained is False and rejected["rejected"][0]["index"] == 1 and "unknown channel" in rejected["rejected"][0]["reason"]


@pytest.mark.parametrize("payload, code, fragment", [
    (b"not json", "invalid", "not valid JSON"),
    (b"\xff\xfe", "invalid", "not valid JSON"),
    (b'"just a string"', "invalid", ""),
    (b"{}", "invalid", ""),
])
def test_bad_payloads_are_refused_not_fatal(handler, payload, code, fragment):
    register(handler)
    rejected, _ = decode(handler.handle(topic("E1", "readings"), payload))["rejected"]
    assert rejected["code"] == code and fragment in rejected["error"]


def test_unknown_asset_conflicting_type_and_bad_register(handler):
    rows, _ = engine_rows(n=2)
    assert decode(handler.handle(topic("ghost", "readings"), json.dumps(rows).encode()))["rejected"][0]["code"] == "not_found"
    register(handler)
    assert decode(register(handler, type_id="brushed_dc_motor"))["rejected"][0]["code"] == "conflict"
    assert "type_id" in decode(handler.handle(topic("E2", "register"), b"{}"))["rejected"][0]["error"]
    assert decode(register(handler, asset_id="E3", type_id="toaster"))["rejected"][0]["code"] == "invalid"


def test_failure_message_marks_the_asset_failed(handler):
    register(handler)
    rows, _ = engine_rows(n=40)
    handler.handle(topic("E1", "readings"), json.dumps(rows).encode())
    no_age = decode(handler.handle(topic("E1", "failure"), json.dumps({"ts": rows[-1]["ts"]}).encode()))
    assert "age is required" in no_age["rejected"][0]["error"]
    body = json.dumps({"ts": rows[-1]["ts"], "age": rows[-1]["age"], "mode": "HPC"}).encode()
    assert decode(handler.handle(topic("E1", "failure"), body))["state"][0]["status"] == "Failed"


def test_an_internal_error_never_escapes(handler, monkeypatch):
    register(handler)
    monkeypatch.setattr(ingest, "ingest_readings", lambda *a, **k: 1 / 0)
    out = handler.handle(topic("E1", "readings"), b'{"ts": "2024-01-01", "age": 1, "values": {"s2": 1}}')
    assert decode(out)["rejected"][0]["code"] == "internal"


def test_messages_on_other_topics_are_ignored(handler):
    assert handler.handle("pdm/v1/assets/E1/state", b"{}") == []
    assert handler.handle("something/else", b"{}") == []


def test_config_from_environment():
    assert MqttConfig.from_env({}) is None
    cfg = MqttConfig.from_env({"PDM_MQTT_HOST": "broker.example.com"})
    assert (cfg.host, cfg.port, cfg.tls, cfg.client_id) == ("broker.example.com", 1883, False, "pdm-ingest")
    secure = MqttConfig.from_env({"PDM_MQTT_HOST": "b", "PDM_MQTT_PORT": "8883", "PDM_MQTT_USERNAME": "u",
                                  "PDM_MQTT_PASSWORD": "p", "PDM_MQTT_CLIENT_ID": "mine"})
    assert secure.tls is True and (secure.username, secure.password, secure.client_id) == ("u", "p", "mine")
    assert MqttConfig.from_env({"PDM_MQTT_HOST": "b", "PDM_MQTT_PORT": "8883", "PDM_MQTT_TLS": "false"}).tls is False


# ================================================================ with a real broker
@pytest.fixture
def cfg(mqtt_broker, request):
    return MqttConfig(mqtt_broker.host, mqtt_broker.port, client_id=f"test-ingest-{request.node.name[:40]}")


@pytest.fixture
def service(cfg, live_db):
    svc = MqttIngestor(cfg, live_db).start()
    assert svc.connected.is_set(), svc.status()
    yield svc
    svc.stop()


def publisher(cfg, name="pub"):
    client = mqtt_ingest.new_client(cfg, client_id=f"test-{name}-{time.time_ns()}")
    client.connect(cfg.host, cfg.port)
    client.loop_start()
    return client


def listen(cfg, filters):
    got = []
    client = mqtt_ingest.new_client(cfg, client_id=f"test-listen-{time.time_ns()}")
    client.on_message = lambda c, u, m: got.append((m.topic, json.loads(m.payload) if m.payload[:1] in b"{[" else m.payload.decode(), m.retain))
    client.connect(cfg.host, cfg.port)
    client.subscribe([(f, 1) for f in filters])
    client.loop_start()
    return client, got


def send(client, asset_id, kind, body):
    info = client.publish(topic(asset_id, kind), json.dumps(body), qos=1)
    info.wait_for_publish(10)
    assert info.is_published()


def test_the_service_announces_itself_and_answers_on_the_state_topic(service, cfg):
    watcher, got = listen(cfg, ["pdm/v1/service/status", "pdm/v1/assets/+/state", "pdm/v1/assets/+/rejected"])
    pub = publisher(cfg)
    try:
        assert wait_for(lambda: any(t.endswith("service/status") and p == "online" for t, p, _ in got))
        send(pub, "E1", "register", {"type_id": "turbofan_engine", "source": "NASA C-MAPSS FD001"})
        assert wait_for(lambda: any(t.endswith("E1/state") for t, _, _ in got))
        send(pub, "ghost", "readings", {"ts": "2024-01-01", "age": 1, "values": {"s2": 1}})
        assert wait_for(lambda: any(t.endswith("ghost/rejected") and p["code"] == "not_found" for t, p, _ in got))
    finally:
        pub.loop_stop(); watcher.loop_stop()


def test_a_device_streams_readings_and_the_asset_is_scored(service, cfg, live_db):
    pub = publisher(cfg)
    try:
        send(pub, "E1", "register", {"type_id": "turbofan_engine", "source": "NASA C-MAPSS FD001"})
        rows, _ = engine_rows()
        watcher, seen = listen(cfg, ["pdm/v1/assets/E1/state"])
        for i in range(0, len(rows), 25):
            send(pub, "E1", "readings", {"readings": rows[i:i + 25]})
        # the service publishes the state only after it has stored and scored the batch
        assert wait_for(lambda: any(p["state"] and p["state"]["readings"] == len(rows) for _, p, _ in seen
                                    if isinstance(p, dict) and "state" in p))
        watcher.loop_stop()
        assert len(db.get_series("E1", live_db)) == len(rows)
        state = ingest.asset_state("E1", live_db)
        assert state["method"] == "learned" and state["status"] == "Warning"
    finally:
        pub.loop_stop()
    # a subscriber that arrives later gets the retained state at once
    late, got = listen(cfg, ["pdm/v1/assets/E1/state"])
    try:
        assert wait_for(lambda: any(r for _, _, r in got))
        assert got[-1][1]["state"]["readings"] == len(rows)
    finally:
        late.loop_stop()


def test_redelivered_messages_are_not_counted_twice(service, cfg, live_db):
    pub = publisher(cfg)
    try:
        send(pub, "E1", "register", {"type_id": "turbofan_engine", "source": "NASA C-MAPSS FD001"})
        rows, _ = engine_rows(n=30)
        send(pub, "E1", "readings", {"readings": rows})
        send(pub, "E1", "readings", {"readings": rows})          # what a redelivery after a missed ack looks like
        assert wait_for(lambda: service.processed >= 3)
        assert len(db.get_series("E1", live_db)) == 30
    finally:
        pub.loop_stop()


def test_messages_sent_while_the_service_is_down_are_processed_when_it_returns(cfg, live_db, mqtt_broker):
    if not mqtt_broker.persistent_sessions:
        pytest.skip(f"the {mqtt_broker.kind} broker does not queue messages for offline sessions (Mosquitto does)")
    first = MqttIngestor(cfg, live_db).start()
    assert first.connected.is_set()
    pub = publisher(cfg)
    try:
        send(pub, "E1", "register", {"type_id": "turbofan_engine", "source": "NASA C-MAPSS FD001"})
        assert wait_for(lambda: db.asset_exists("E1", live_db))
        first.stop()                                              # the service goes away; its session stays on the broker
        rows, _ = engine_rows(n=30)
        send(pub, "E1", "readings", {"readings": rows})            # nobody is listening right now
        time.sleep(0.5)
        assert db.get_series("E1", live_db).empty
        second = MqttIngestor(cfg, live_db).start()                # same client id: picks the session up again
        try:
            assert wait_for(lambda: len(db.get_series("E1", live_db)) == 30)
        finally:
            second.stop()
    finally:
        pub.loop_stop()


def test_the_simulator_streams_over_mqtt_end_to_end(service, cfg, live_db):
    feeds = simulator.build_feeds(2)
    sink = simulator.MqttSink(cfg)
    feed = simulator.LiveFeed(feeds, sink, interval_s=0, step=50)
    feed.run()
    assert feed.status()["done"] and feed.errors == 0, feed.status()
    for f in feeds:
        assert wait_for(lambda f=f: ingest.asset_state(f.asset_id, live_db)["readings"] == f.total), service.status()
    for f in feeds:
        assert wait_for(lambda f=f: ingest.asset_state(f.asset_id, live_db)["method"] == "learned")
        state = ingest.asset_state(f.asset_id, live_db)
        assert state["method"] == "learned" and state["status"] != "Learning"
        assert db.get_asset(f.asset_id, live_db)["metadata"]["live"] is True


def test_the_motor_breakdown_travels_over_mqtt_too(service, cfg, live_db):
    feed = simulator.LiveFeed(simulator.build_feeds(0, include_motor=True), simulator.MqttSink(cfg), interval_s=0, step=200)
    feed.run()
    assert wait_for(lambda: ingest.asset_state("LIVE-MTR-01", live_db)["status"] == "Failed")


def test_the_simulator_sees_what_the_service_refuses(service, cfg):
    sink = simulator.MqttSink(cfg)
    try:
        sink.send("not-registered", [{"ts": "2024-01-01", "age": 1, "values": {"s2": 1}}])
        assert wait_for(lambda: len(sink.rejections) == 1)
        assert "not_found" in sink.rejections[0][1]
    finally:
        sink.close()


def test_an_unreachable_broker_is_an_error_not_a_hang():
    with pytest.raises((ConnectionError, OSError)):
        simulator.MqttSink(MqttConfig("127.0.0.1", 1), timeout=2)


def test_two_services_on_one_broker_do_not_store_a_reading_twice(cfg, live_db, mqtt_broker):
    """A dashboard that runs its own subscriber plus a standalone service, with different client ids: both receive
    every message. Both write to the same database; each reading must end up there once."""
    asset = f"TWO-{time.time_ns()}"        # its own asset: some brokers hand stale messages of earlier tests to new sessions
    first = MqttIngestor(cfg, live_db).start()
    second = MqttIngestor(MqttConfig(cfg.host, cfg.port, client_id=cfg.client_id + "-b"), live_db).start()
    pub = publisher(cfg)
    try:
        assert first.connected.is_set() and second.connected.is_set()
        send(pub, asset, "register", {"type_id": "turbofan_engine", "source": "NASA C-MAPSS FD001"})
        rows, _ = engine_rows(n=60)
        for i in range(0, 60, 10):
            send(pub, asset, "readings", {"readings": rows[i:i + 10]})
        assert wait_for(lambda: len(db.get_series(asset, live_db)) == 60)
        time.sleep(1.5)                    # a late second copy would show up now
        assert len(db.get_series(asset, live_db)) == 60
        assert not first.last_error and not second.last_error
    finally:
        pub.loop_stop()
        first.stop()
        second.stop()
