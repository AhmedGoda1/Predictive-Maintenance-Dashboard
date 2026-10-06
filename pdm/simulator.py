"""Simulated sensors: stream recorded runs into the system as if the assets were measured right now.

There is no real equipment in this project, so this stands in for the devices. Readings leave the
simulator in the shape a gateway would send them (time of measurement, age, channel values) and reach
the system through the same ingestion path as real data, either

  * in-process (`LocalSink`): calls `pdm.ingest` directly; used by the dashboard's demo feed when no
    broker is configured, or
  * over MQTT (`MqttSink`): publishes to a broker, where the ingestion service (`pdm.mqtt_ingest`)
    picks the readings up; used by `scripts/simulate.py`, exactly as a real device or gateway would.

The recorded timestamps are replaced by the current time, so alerts, ages and the live dashboard
behave as they would with real data. Engines come from the held-out C-MAPSS test set (the RUL model
never saw them); each starts from cycle 1, so an engine can be watched going from Healthy towards
Critical. The motor is streamed with its recorded seconds as age and, because the run ended in a
breakdown, its failure is reported at the end, as an operator would log it.
"""
import json
import logging
import threading
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

from . import db, ingest
from .datasets import cmapss, motor
from .datasets.base import Run

log = logging.getLogger("pdm.simulator")

LIVE_PREFIX = "LIVE-"
ENGINE_TARGETS = (12, 45, 80, 115)       # remaining life (cycles) at the end of the recording that the demo engines aim for
OFFLINE_FLEET_STRIDE = 5                 # the recorded fleet loaded by the pipeline uses units 1, 6, 11, ...


# ---------------------------------------------------------------- what to stream
@dataclass
class Feed:
    asset_id: str
    run: Run
    name: str

    @property
    def total(self) -> int:
        return len(self.run.series)


def pick_engines(n: int, subset: str = "FD001") -> list:
    """Test engines whose recordings end at a spread of remaining lives (so some turn Critical, some stay Healthy)."""
    final = {int(u): float(r) for u, r in enumerate(
        np.loadtxt(cmapss._path("RUL", subset, cmapss.DATA_DIR), ndmin=1), start=1)}
    free = [u for u in final if (u - 1) % OFFLINE_FLEET_STRIDE]          # not already in the recorded fleet
    chosen = []
    for target in (ENGINE_TARGETS * ((n // len(ENGINE_TARGETS)) + 1))[:n]:
        best = min((u for u in free if u not in chosen), key=lambda u: abs(final[u] - target))
        chosen.append(best)
    return chosen


def build_feeds(n_engines: int = 4, include_motor: bool = False, subset: str = "FD001") -> list:
    feeds = []
    if n_engines:
        units = pick_engines(n_engines, subset)
        for run in cmapss.load(subset, "test", units=set(units)):
            unit = run.metadata["unit"]
            feeds.append(Feed(f"{LIVE_PREFIX}{subset}-{unit:03d}", run, f"Live engine {unit:03d} ({subset})"))
    if include_motor:
        feeds.append(Feed(f"{LIVE_PREFIX}MTR-01", motor.load(), "Live brushed DC motor"))
    return feeds


def payload(feed: Feed, start: int, count: int, now: datetime) -> list:
    """Readings `start .. start+count` of a feed, stamped with the current time (one millisecond apart)."""
    t = feed.run.series
    cols = [c for c in t.columns if c not in ("ts", "age")]
    out = []
    for k, (_, row) in enumerate(t.iloc[start:start + count].iterrows()):
        values = {c: float(row[c]) for c in cols if np.isfinite(row[c])}
        out.append({"ts": (now + timedelta(milliseconds=k)).isoformat(), "age": float(row["age"]), "values": values})
    return out


# ---------------------------------------------------------------- where it goes
class LocalSink:
    """Hands readings straight to the ingestion code in this process."""

    def __init__(self, db_path=None):
        self.db_path = db_path

    def register(self, feed: Feed, reset: bool = False) -> None:
        if reset and db.asset_exists(feed.asset_id, self.db_path):
            db.delete_asset(feed.asset_id, self.db_path)
        ingest.register_asset(feed.asset_id, feed.run.type_id, feed.name, source=feed.run.source,
                              metadata={"live": True, "feed": "simulator"}, db_path=self.db_path)

    def send(self, asset_id: str, readings: list) -> dict:
        return ingest.ingest_readings(asset_id, readings, self.db_path).to_dict()

    def failure(self, asset_id: str, ts, age, mode=None) -> dict:
        return ingest.report_failure(asset_id, ts, age, mode, self.db_path)


class MqttSink:
    """Publishes readings to an MQTT broker (QoS 1: each publish waits for the broker's acknowledgement).

    Listens for `rejected` messages of the ingestion service so refused data does not go unnoticed.
    Over MQTT an asset cannot be deleted, so a restarted feed re-registers the same assets and
    readings older than what is stored are refused as out of order.
    """

    def __init__(self, cfg, client_id: str = None, timeout: float = 15):
        from . import mqtt_ingest
        self.mq, self.timeout = mqtt_ingest, timeout
        self.rejections = deque(maxlen=50)
        self._connected = threading.Event()
        self.client = mqtt_ingest.new_client(cfg, client_id=client_id or f"pdm-sim-{uuid.uuid4().hex[:8]}")
        self.client.on_connect = self._on_connect
        self.client.on_message = lambda c, u, m: self.rejections.append((m.topic, m.payload.decode(errors="replace")[:300]))
        self.client.connect(cfg.host, cfg.port, cfg.keepalive)
        self.client.loop_start()
        if not self._connected.wait(timeout):
            self.close()
            raise ConnectionError(f"could not connect to the MQTT broker at {cfg.host}:{cfg.port}")

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if not reason_code.is_failure:
            client.subscribe(f"{self.mq.ROOT}/assets/+/rejected", qos=1)
            self._connected.set()

    def _publish(self, asset_id: str, kind: str, body: dict) -> None:
        info = self.client.publish(self.mq.topic(asset_id, kind), json.dumps(body), qos=1)
        info.wait_for_publish(self.timeout)
        if not info.is_published():
            raise TimeoutError(f"broker did not acknowledge the {kind} message of {asset_id}")

    def register(self, feed: Feed, reset: bool = False) -> None:
        self._publish(feed.asset_id, "register", {"type_id": feed.run.type_id, "name": feed.name,
                                                  "source": feed.run.source, "metadata": {"live": True, "feed": "simulator"}})

    def send(self, asset_id: str, readings: list) -> None:
        self._publish(asset_id, "readings", {"readings": readings})

    def failure(self, asset_id: str, ts, age, mode=None) -> None:
        self._publish(asset_id, "failure", {"ts": str(ts), "age": age, "mode": mode})

    def close(self) -> None:
        self.client.disconnect()
        self.client.loop_stop()


# ---------------------------------------------------------------- the feed
class LiveFeed:
    """Sends the next `step` readings of every feed each `interval_s` seconds until the recordings end."""

    def __init__(self, feeds: list, sink, interval_s: float = 1.0, step: int = 1, reset: bool = True):
        self.feeds, self.sink, self.interval_s, self.step, self.reset = feeds, sink, interval_s, max(1, step), reset
        self.sent = {f.asset_id: 0 for f in feeds}
        self._last_ts = {}                      # newest timestamp sent per asset: stamps must keep increasing
        self.errors = 0
        self.last_error = ""
        self._stop = threading.Event()
        self._thread = None
        self._failure_reported = set()

    # -- control
    def start(self) -> "LiveFeed":
        self._thread = threading.Thread(target=self.run, name="live-feed", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def status(self) -> dict:
        total = {f.asset_id: f.total for f in self.feeds}
        return {"running": self.running, "done": all(self.sent[a] >= total[a] for a in total),
                "sent": dict(self.sent), "total": total, "errors": self.errors, "last_error": self.last_error,
                "refused": list(getattr(self.sink, "rejections", []))[-3:]}

    # -- the loop
    def run(self) -> None:
        """Streams until every recording is sent or stop() is called (blocking; start() runs it in a thread)."""
        try:
            self._stream()
        finally:
            getattr(self.sink, "close", lambda: None)()

    def _stream(self) -> None:
        try:
            for f in self.feeds:
                self.sink.register(f, self.reset)
        except Exception as e:
            self.errors += 1
            self.last_error = f"registering assets: {e}"
            log.error(self.last_error)
            return
        while not self._stop.is_set():
            pending = False
            for f in self.feeds:
                i = self.sent[f.asset_id]
                if i >= f.total:
                    self._report_failure(f)
                    continue
                pending = True
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                if f.asset_id in self._last_ts:                # never start a batch before the previous one ended
                    now = max(now, self._last_ts[f.asset_id] + timedelta(milliseconds=1))
                batch = payload(f, i, self.step, now)
                try:
                    self.sink.send(f.asset_id, batch)
                    self.sent[f.asset_id] = i + len(batch)
                    self._last_ts[f.asset_id] = now + timedelta(milliseconds=len(batch) - 1)
                except Exception as e:                      # keep streaming the other assets; retry this one next tick
                    self.errors += 1
                    self.last_error = f"{f.asset_id}: {e}"
                    log.warning(self.last_error)
            if not pending:
                break
            self._stop.wait(self.interval_s)

    def _report_failure(self, f: Feed) -> None:
        """When a run that ended in a breakdown has been streamed completely, log the breakdown."""
        if f.asset_id in self._failure_reported or not f.run.failure_observed or f.run.failure_age is None:
            return
        self._failure_reported.add(f.asset_id)
        try:
            self.sink.failure(f.asset_id, datetime.now(timezone.utc).replace(tzinfo=None), f.run.failure_age, "run to failure")
        except Exception as e:
            self.errors += 1
            self.last_error = f"{f.asset_id}: failure report: {e}"


def reset_live_assets(db_path=None) -> int:
    """Deletes every simulated live asset; returns how many were removed."""
    ids = [a for a in db.list_assets(db_path=db_path)["asset_id"] if a.startswith(LIVE_PREFIX)]
    for a in ids:
        db.delete_asset(a, db_path)
    return len(ids)
