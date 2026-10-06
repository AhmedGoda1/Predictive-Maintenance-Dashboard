import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dashboard"))      # the dashboard modules are imported by name (data_source, utils, ...)


@pytest.fixture(scope="session")
def built_db(tmp_path_factory):
    """A database built once from the datasets and shared by the pipeline and dashboard tests."""
    from pdm import pipeline
    path = tmp_path_factory.mktemp("db") / "maintenance.db"
    pipeline.build(path)
    return path


@pytest.fixture
def live_db(tmp_path):
    """An empty database (schema + asset types) with the committed FD001 RUL model registered, as a deployment has."""
    import json
    from pdm import db
    path = tmp_path / "live.db"
    db.init_db(path)
    db.mark_current(path)                      # what the ingestion service does when it creates the database
    metrics = json.loads((ROOT / "models" / "cmapss_metrics.json").read_text())["FD001"]
    db.register_model("turbofan_FD001", "turbofan_engine", "learned", source="NASA C-MAPSS FD001 train engines",
                      artifact_path="models/turbofan_FD001.joblib", metrics=metrics, db_path=path)
    return path


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Broker(NamedTuple):
    host: str
    port: int
    kind: str                    # mosquitto | amqtt | external
    persistent_sessions: bool    # does it keep messages for a disconnected persistent session?


def _wait_for_port(port: int, timeout: float = 10.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise RuntimeError(f"nothing is listening on port {port}")


def _queues_for_offline_sessions(host: str, port: int) -> bool:
    """Probe: does the broker keep QoS 1 messages for a persistent session that is offline?"""
    import paho.mqtt.client as mqtt

    def client(cid, persistent, got=None):
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid, clean_session=not persistent)
        if got is not None:
            c.on_message = lambda cl, u, m: got.append(m.payload)
        return c

    tag = f"probe{time.time_ns()}"
    a = client(tag, True)
    a.connect(host, port)
    a.subscribe(f"{tag}/#", qos=1)
    a.loop_start()
    time.sleep(0.4)
    a.disconnect()
    a.loop_stop()
    p = client(tag + "p", False)
    p.connect(host, port)
    p.loop_start()
    p.publish(f"{tag}/x", b"1", qos=1).wait_for_publish(5)
    p.loop_stop()
    got = []
    b = client(tag, True, got)
    b.connect(host, port)
    b.loop_start()
    time.sleep(1.0)
    b.disconnect()
    b.loop_stop()
    return bool(got)


@pytest.fixture(scope="session")
def mqtt_broker(tmp_path_factory):
    """A real MQTT broker for the integration tests, as a Broker(host, port, kind, persistent_sessions).

    Preference: PDM_TEST_BROKER=host:port (an existing broker), then a local `mosquitto` binary, then the
    pure-Python amqtt broker (interpreter in PDM_TEST_BROKER_PYTHON, default the current one; it does not
    queue messages for offline sessions). Skips when none is available.
    """
    external = os.environ.get("PDM_TEST_BROKER")
    if external:
        host, port = external.split(":")
        yield Broker(host, int(port), "external", _queues_for_offline_sessions(host, int(port)))
        return
    port = _free_port()
    if shutil.which("mosquitto"):
        conf = tmp_path_factory.mktemp("mosquitto") / "mosquitto.conf"
        conf.write_text(f"listener {port} 127.0.0.1\nallow_anonymous true\npersistence false\n")
        proc = subprocess.Popen(["mosquitto", "-c", str(conf)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        kind = "mosquitto"
        try:
            _wait_for_port(port)
        except Exception:
            proc.terminate()
            raise
    else:
        python = os.environ.get("PDM_TEST_BROKER_PYTHON", sys.executable)
        if subprocess.run([python, "-c", "import amqtt"], capture_output=True).returncode != 0:
            pytest.skip("no MQTT broker: install mosquitto, or pip install amqtt, or set PDM_TEST_BROKER=host:port")
        proc = subprocess.Popen([python, str(ROOT / "tests" / "amqtt_broker.py"), str(port)],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        assert proc.stdout.readline().strip() == "READY", "the test broker did not start"
        kind = "amqtt"
    try:
        yield Broker("127.0.0.1", port, kind, _queues_for_offline_sessions("127.0.0.1", port))
    finally:
        proc.terminate()
        proc.wait(timeout=10)
