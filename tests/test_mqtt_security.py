"""The security setup recommended in pdm/mqtt_ingest.py, run against a real Mosquitto broker:
TLS, a password per client, and ACLs that confine each device to its own inbound topics."""
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import paho.mqtt.client as mqtt
import pytest

from pdm import db, mqtt_ingest
from pdm.mqtt_ingest import MqttConfig, MqttIngestor, topic
from test_ingest import engine_rows
from test_mqtt import wait_for

pytestmark = pytest.mark.skipif(not (shutil.which("mosquitto") and shutil.which("openssl") and shutil.which("mosquitto_passwd")),
                                reason="needs mosquitto, mosquitto_passwd and openssl")

ACL = """\
user pdm-service
topic read pdm/v1/assets/+/register
topic read pdm/v1/assets/+/readings
topic read pdm/v1/assets/+/failure
topic write pdm/v1/assets/+/state
topic write pdm/v1/assets/+/rejected
topic write pdm/v1/service/status

user dev-e1
topic write pdm/v1/assets/E1/register
topic write pdm/v1/assets/E1/readings
topic write pdm/v1/assets/E1/failure
topic read pdm/v1/assets/E1/state
topic read pdm/v1/assets/E1/rejected

user dev-e2
topic write pdm/v1/assets/E2/readings
"""


@pytest.fixture(scope="module")
def secure():
    from conftest import _free_port, _wait_for_port
    # Mosquitto started by root drops to its own user, which must be able to read these (throwaway) files
    d = Path(tempfile.mkdtemp(prefix="pdm-mosquitto-"))
    d.chmod(0o755)
    run = lambda *a: subprocess.run(a, cwd=d, check=True, capture_output=True)
    run("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "ca.key", "-out", "ca.crt",
        "-days", "2", "-subj", "/CN=test-ca")
    run("openssl", "req", "-newkey", "rsa:2048", "-nodes", "-keyout", "server.key", "-out", "server.csr", "-subj", "/CN=localhost")
    (d / "san.cnf").write_text("subjectAltName=DNS:localhost,IP:127.0.0.1\n")
    run("openssl", "x509", "-req", "-in", "server.csr", "-CA", "ca.crt", "-CAkey", "ca.key", "-CAcreateserial",
        "-out", "server.crt", "-days", "2", "-extfile", "san.cnf")
    run("mosquitto_passwd", "-b", "-c", "passwords", "pdm-service", "svc-secret")
    run("mosquitto_passwd", "-b", "passwords", "dev-e1", "e1-secret")
    run("mosquitto_passwd", "-b", "passwords", "dev-e2", "e2-secret")
    (d / "acl").write_text(ACL)
    for f in d.iterdir():
        f.chmod(0o644)
    port = _free_port()
    (d / "mosquitto.conf").write_text(
        f"listener {port} 127.0.0.1\nallow_anonymous false\npassword_file {d/'passwords'}\nacl_file {d/'acl'}\n"
        f"cafile {d/'ca.crt'}\ncertfile {d/'server.crt'}\nkeyfile {d/'server.key'}\npersistence false\n")
    proc = subprocess.Popen(["mosquitto", "-c", str(d / "mosquitto.conf")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _wait_for_port(port)
        yield {"port": port, "ca": str(d / "ca.crt")}
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(d, ignore_errors=True)


def cfg_for(secure, user, password, client_id, **kw):
    return MqttConfig("127.0.0.1", secure["port"], username=user, password=password, tls=True,
                      ca_certs=secure["ca"], client_id=client_id, **kw)


def device(secure, user, password):
    c = mqtt_ingest.new_client(cfg_for(secure, user, password, f"{user}-{time.time_ns()}"))
    c.connect("127.0.0.1", secure["port"])
    c.loop_start()
    return c


@pytest.fixture
def service(secure, live_db):
    svc = MqttIngestor(cfg_for(secure, "pdm-service", "svc-secret", "sec-service"), live_db).start()
    assert svc.connected.is_set(), svc.status()
    yield svc
    svc.stop()


def publish(client, t, body):
    info = client.publish(t, json.dumps(body), qos=1)
    info.wait_for_publish(10)


def test_a_device_streams_over_tls_with_its_own_credentials(service, live_db):
    dev = device(service.cfg and {"port": service.cfg.port, "ca": service.cfg.ca_certs}, "dev-e1", "e1-secret")
    try:
        publish(dev, topic("E1", "register"), {"type_id": "turbofan_engine", "source": "NASA C-MAPSS FD001"})
        rows, _ = engine_rows(n=30)
        publish(dev, topic("E1", "readings"), {"readings": rows})
        assert wait_for(lambda: len(db.get_series("E1", live_db)) == 30)
    finally:
        dev.loop_stop()


def test_wrong_password_and_missing_tls_are_refused(secure, live_db):
    bad = MqttIngestor(cfg_for(secure, "pdm-service", "wrong", "sec-bad"), live_db).start(wait=3)
    try:
        assert not bad.connected.is_set() and "refused" in bad.last_error
    finally:
        bad.stop()
    plain = MqttConfig("127.0.0.1", secure["port"], username="pdm-service", password="svc-secret", tls=False,
                       client_id="sec-plain")
    attempt = MqttIngestor(plain, live_db).start(wait=3)
    try:
        assert not attempt.connected.is_set()                      # a plaintext client cannot talk to the TLS listener
    finally:
        attempt.stop()


def test_a_client_that_does_not_trust_the_server_certificate_is_refused(secure, live_db):
    cfg = cfg_for(secure, "pdm-service", "svc-secret", "sec-untrusted")
    cfg.ca_certs = None                                            # system CAs only: the test CA is not among them
    svc = MqttIngestor(cfg, live_db).start(wait=3)
    try:
        assert not svc.connected.is_set()
    finally:
        svc.stop()


def test_a_device_cannot_write_to_another_assets_topics(secure, service, live_db):
    dev = device(secure, "dev-e1", "e1-secret")
    try:
        before = service.received
        publish(dev, topic("E1", "register"), {"type_id": "turbofan_engine", "source": "NASA C-MAPSS FD001"})
        assert wait_for(lambda: service.received > before)
        mark = service.received
        rows, _ = engine_rows(n=3)
        publish(dev, topic("E2", "readings"), {"readings": rows})   # not this device's asset
        time.sleep(1.5)
        assert service.received == mark                            # the broker dropped it; the service never saw it
        assert not db.asset_exists("E2", live_db)
    finally:
        dev.loop_stop()


def test_a_device_cannot_forge_the_services_answers(secure, service):
    dev = device(secure, "dev-e1", "e1-secret")
    got = []
    dev.on_message = lambda c, u, m: got.append(m.payload)
    dev.subscribe([(topic("E1", "state"), 1), (topic("E1", "rejected"), 1)])
    try:
        publish(dev, topic("E1", "state"), {"state": {"status": "Healthy"}, "forged": True})
        publish(dev, topic("E1", "rejected"), {"error": "forged"})
        time.sleep(1.5)
        assert all(b"forged" not in m for m in got)                # neither forgery reached any subscriber
        assert not any(b'"Healthy"' in m for m in got)             # (the retained state the service published is genuine)
    finally:
        dev.loop_stop()


def test_a_device_cannot_read_other_assets_state(secure, service):
    dev = device(secure, "dev-e2", "e2-secret")
    got = []
    dev.on_message = lambda c, u, m: got.append(m.topic)
    dev.subscribe([(topic("E1", "state"), 1), ("pdm/v1/assets/+/state", 1)])
    publisher = device(secure, "dev-e1", "e1-secret")
    try:
        publish(publisher, topic("E1", "register"), {"type_id": "turbofan_engine", "source": "NASA C-MAPSS FD001"})
        time.sleep(1.5)
        assert not got                                             # dev-e2 has no read permission on any state topic
    finally:
        dev.loop_stop(); publisher.loop_stop()
