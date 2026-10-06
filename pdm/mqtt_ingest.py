"""MQTT ingestion service.

Devices (or a gateway) publish to a broker; this service subscribes, validates, stores and scores.

Topics (JSON payloads), `<id>` is the asset id (letters, digits, `.`, `_`, `-`; at most 64):

  inbound  pdm/v1/assets/<id>/register   {"type_id": "turbofan_engine", "name": "...", "site": "...",
                                          "source": "...", "metadata": {...}}
           pdm/v1/assets/<id>/readings   one reading {"ts": "2024-05-01T12:00:00Z", "age": 31,
                                          "values": {"s2": 642.1, ...}}, or {"readings": [...]},
                                          or a list of readings (at most 1000)
           pdm/v1/assets/<id>/failure    {"ts": "...", "age": 148, "mode": "HPC"}
  outbound pdm/v1/assets/<id>/state      current status, health index and RUL estimate, with the
                                          counts of the last message (retained: a new subscriber gets it at once)
           pdm/v1/assets/<id>/rejected   what was refused and why (not retained)
           pdm/v1/service/status         "online" / "offline" (retained; "offline" is the last will)

Delivery: messages are consumed with QoS 1 over a persistent session (fixed client id, clean_session off)
and acknowledged to the broker only after they are processed. If the service is down, the broker keeps
the messages; if it dies mid-message, the broker redelivers. Ingestion is idempotent (same timestamp =
duplicate), so redelivery never double-counts.

Security: use a broker with TLS and per-device credentials, and restrict each device by ACL to
`pdm/v1/assets/<its id>/#`. This service needs read access to the inbound topics and write access to the
`state`, `rejected` and `service/status` topics. Configuration comes from environment variables, see
`MqttConfig.from_env`.

Run:  PDM_MQTT_HOST=broker.example.com PDM_MQTT_USERNAME=... PDM_MQTT_PASSWORD=... python -m pdm.mqtt_ingest
"""
import json
import logging
import os
import queue
import re
import threading
from dataclasses import dataclass
from typing import Optional

import paho.mqtt.client as mqtt

from . import db, ingest, pipeline

log = logging.getLogger("pdm.mqtt")

ROOT = "pdm/v1"
ASSET_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
INBOUND_KINDS = ("register", "readings", "failure")
SUBSCRIPTIONS = [f"{ROOT}/assets/+/{kind}" for kind in INBOUND_KINDS]
STATUS_TOPIC = f"{ROOT}/service/status"


def topic(asset_id: str, kind: str) -> str:
    return f"{ROOT}/assets/{asset_id}/{kind}"


@dataclass
class MqttConfig:
    host: str
    port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None
    tls: bool = False
    ca_certs: Optional[str] = None
    client_id: str = "pdm-ingest"
    keepalive: int = 60

    @staticmethod
    def from_env(env=None, default_client_id: str = "pdm-ingest") -> Optional["MqttConfig"]:
        """Reads PDM_MQTT_HOST, _PORT, _USERNAME, _PASSWORD, _TLS (true/false), _CA_CERTS, _CLIENT_ID.

        Returns None when PDM_MQTT_HOST is not set. TLS defaults to on for port 8883.
        """
        env = os.environ if env is None else env
        host = env.get("PDM_MQTT_HOST")
        if not host:
            return None
        port = int(env.get("PDM_MQTT_PORT", 1883))
        tls = env.get("PDM_MQTT_TLS")
        return MqttConfig(
            host=host, port=port, username=env.get("PDM_MQTT_USERNAME") or None,
            password=env.get("PDM_MQTT_PASSWORD") or None,
            tls=(port == 8883) if tls is None else tls.strip().lower() in ("1", "true", "yes", "on"),
            ca_certs=env.get("PDM_MQTT_CA_CERTS") or None,
            client_id=env.get("PDM_MQTT_CLIENT_ID") or default_client_id,
        )


def config_from_options(host=None, port=None, username=None, password=None, tls=False, env=None) -> Optional[MqttConfig]:
    """Broker settings from command-line style options; anything not given comes from the PDM_MQTT_* variables."""
    env = dict(os.environ if env is None else env)
    for value, var in [(host, "PDM_MQTT_HOST"), (port, "PDM_MQTT_PORT"), (username, "PDM_MQTT_USERNAME"),
                       (password, "PDM_MQTT_PASSWORD")]:
        if value:
            env[var] = str(value)
    if tls:
        env["PDM_MQTT_TLS"] = "true"
    return MqttConfig.from_env(env)


def new_client(cfg: MqttConfig, client_id: str = None, persistent: bool = False, manual_ack: bool = False):
    """A paho client set up with the credentials and TLS of the config (not yet connected)."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id or cfg.client_id,
                         clean_session=not persistent, manual_ack=manual_ack)
    if cfg.username:
        client.username_pw_set(cfg.username, cfg.password)
    if cfg.tls:
        client.tls_set(ca_certs=cfg.ca_certs)
    return client


# ---------------------------------------------------------------- message handling (no network)
class Handler:
    """Turns one inbound message into ingestion calls and the outbound messages to publish."""

    def __init__(self, db_path=None):
        self.db_path = db_path

    @staticmethod
    def parse_topic(t: str):
        """(asset_id, kind) of an inbound topic, or None for anything else."""
        parts = t.split("/")                      # pdm / v1 / assets / <id> / <kind>
        if len(parts) != 5 or "/".join(parts[:3]) != f"{ROOT}/assets":
            return None
        asset_id, kind = parts[3], parts[4]
        if kind not in INBOUND_KINDS or not ASSET_ID.match(asset_id):
            return None
        return asset_id, kind

    def handle(self, t: str, payload: bytes) -> list:
        """Processes a message; returns [(topic, payload bytes, retain)] to publish. Never raises."""
        parsed = self.parse_topic(t)
        if parsed is None:
            return []
        asset_id, kind = parsed
        try:
            body = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            return [self._rejected(asset_id, "payload is not valid JSON")]
        try:
            if kind == "register":
                return self._register(asset_id, body)
            if kind == "readings":
                return self._readings(asset_id, body)
            return self._failure(asset_id, body)
        except ingest.NotFound as e:
            return [self._rejected(asset_id, str(e), "not_found")]
        except ingest.Conflict as e:
            return [self._rejected(asset_id, str(e), "conflict")]
        except (ingest.IngestError, ValueError, TypeError) as e:
            return [self._rejected(asset_id, str(e), "invalid")]
        except Exception:                                    # a bad message must never stop the service
            log.exception("internal error handling %s", t)
            return [self._rejected(asset_id, "internal error", "internal")]

    # -- kinds
    def _register(self, asset_id, body):
        if not isinstance(body, dict) or "type_id" not in body:
            raise ingest.IngestError("register needs an object with type_id")
        ingest.register_asset(asset_id, body["type_id"], body.get("name"), body.get("site"), body.get("source"),
                              body.get("metadata") or {}, self.db_path)
        return [self._state(asset_id, ingest.asset_state(asset_id, self.db_path))]

    def _readings(self, asset_id, body):
        if isinstance(body, dict) and "readings" in body:
            readings = body["readings"]
        elif isinstance(body, dict):
            readings = [body]
        else:
            readings = body
        result = ingest.ingest_readings(asset_id, readings, self.db_path).to_dict()
        out = [self._state(asset_id, result)]
        if result["rejected"] or result["scoring_error"]:
            out.append(self._rejected(asset_id, "some readings were refused", "invalid",
                                      rejected=result["rejected"], scoring_error=result["scoring_error"]))
        return out

    def _failure(self, asset_id, body):
        if not isinstance(body, dict) or "ts" not in body:
            raise ingest.IngestError("failure needs an object with ts")
        state = ingest.report_failure(asset_id, body["ts"], body.get("age"), body.get("mode"), self.db_path)
        return [self._state(asset_id, state)]

    # -- outbound
    @staticmethod
    def _state(asset_id, content):
        return (topic(asset_id, "state"), json.dumps(content, default=str).encode(), True)

    @staticmethod
    def _rejected(asset_id, error, code="invalid", **extra):
        body = {"error": error, "code": code, **{k: v for k, v in extra.items() if v}}
        return (topic(asset_id, "rejected"), json.dumps(body, default=str).encode(), False)


# ---------------------------------------------------------------- the service
class MqttIngestor:
    """Connects to the broker, consumes inbound messages and acknowledges them once processed."""

    def __init__(self, cfg: MqttConfig, db_path=None, queue_size: int = 10000):
        self.cfg = cfg
        self.handler = Handler(db_path)
        self.db_path = db_path
        self._queue = queue.Queue(queue_size)
        self._worker = None
        self.connected = threading.Event()
        self.received = 0
        self.processed = 0
        self.last_error = ""
        self._refused = False
        self.client = new_client(cfg, persistent=True, manual_ack=True)
        self.client.will_set(STATUS_TOPIC, "offline", qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    # -- lifecycle
    def start(self, wait: float = 10.0) -> "MqttIngestor":
        """Prepares the database, starts the worker and connects (reconnecting by itself if the broker drops)."""
        target = self.db_path or db.DB_NAME
        if not os.path.exists(target):
            db.init_db(self.db_path)
            db.mark_current(self.db_path)
        pipeline.ensure_models(self.db_path)
        self._worker = threading.Thread(target=self._work, name="mqtt-ingest-worker", daemon=True)
        self._worker.start()
        self.client.connect_async(self.cfg.host, self.cfg.port, self.cfg.keepalive)
        self.client.loop_start()
        if wait:
            self.connected.wait(wait)
        return self

    def stop(self) -> None:
        if self.connected.is_set():
            self.client.publish(STATUS_TOPIC, "offline", qos=1, retain=True).wait_for_publish(3)
        self._queue.put(None)
        if self._worker is not None:
            self._worker.join(timeout=10)
        self.client.disconnect()
        self.client.loop_stop()
        self.connected.clear()

    def status(self) -> dict:
        return {"connected": self.connected.is_set(), "broker": f"{self.cfg.host}:{self.cfg.port}",
                "received": self.received, "processed": self.processed, "last_error": self.last_error}

    # -- callbacks (network thread): keep them short
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            self._refused = True                      # keep this reason: the disconnect that follows must not hide it
            self.last_error = f"broker refused the connection: {reason_code}"
            log.error(self.last_error)
            return
        self._refused = False
        client.subscribe([(s, 1) for s in SUBSCRIPTIONS])
        client.publish(STATUS_TOPIC, "online", qos=1, retain=True)
        self.connected.set()
        log.info("connected to %s:%s", self.cfg.host, self.cfg.port)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        self.connected.clear()
        if reason_code.is_failure and not self._refused:
            self.last_error = f"connection lost: {reason_code}"
            log.warning(self.last_error)

    def _on_message(self, client, userdata, msg):
        self.received += 1
        self._queue.put(msg)

    # -- worker thread
    def _work(self) -> None:
        while True:
            msg = self._queue.get()
            if msg is None:
                return
            try:
                for out_topic, payload, retain in self.handler.handle(msg.topic, msg.payload):
                    self.client.publish(out_topic, payload, qos=1, retain=retain)
            except Exception as e:                             # publishing failed: do not ack, the broker redelivers
                self.last_error = f"{type(e).__name__}: {e}"
                log.exception("failed to process %s", msg.topic)
                continue
            self.processed += 1
            if msg.qos > 0:
                self.client.ack(msg.mid, msg.qos)              # only now does the broker forget the message


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = MqttConfig.from_env()
    if cfg is None:
        raise SystemExit("Set PDM_MQTT_HOST (and PDM_MQTT_PORT / _USERNAME / _PASSWORD / _TLS as needed).")
    svc = MqttIngestor(cfg).start()
    log.info("ingesting from %s:%s into %s", cfg.host, cfg.port, svc.db_path or db.DB_NAME)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        svc.stop()


if __name__ == "__main__":
    main()
