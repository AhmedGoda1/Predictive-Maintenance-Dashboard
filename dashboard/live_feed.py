"""Live data in the hosted dashboard.

MQTT is the ingestion path. When a broker is configured (environment variables PDM_MQTT_HOST, ...; on
Streamlit Cloud: the app's secrets), this process also runs the ingestion subscriber (`pdm.mqtt_ingest`),
and the demo feed publishes its simulated sensor readings to that broker, so they travel the same way as
real device data: device -> broker -> ingestion service -> database -> dashboard. Anyone else can publish
to the same topics (see README), e.g. `scripts/simulate.py` from a laptop.

Without a broker the demo feed hands its readings straight to the ingestion code, so the app still
works as a demo (and says so).

One subscriber and one feed exist per process; everyone using the app shares them.
"""
import data_source  # noqa: F401  (puts the repository root on sys.path)
from pdm import db, mqtt_ingest, simulator

DASHBOARD_CLIENT_ID = "pdm-dashboard-ingest"


def mqtt_config():
    """The broker configuration from the environment, or None when no broker is configured."""
    return mqtt_ingest.MqttConfig.from_env(default_client_id=DASHBOARD_CLIENT_ID)


_ingestors = []                      # subscribers started by this process


def start_ingestor():
    """Starts the ingestion subscriber when a broker is configured; returns it (or None).

    There is only ever one: a subscriber left over from before a code update is stopped first. Two with the
    same client id would take the broker session from each other again and again.
    """
    stop_ingestors()
    cfg = mqtt_config()
    if cfg is None:
        return None
    ingestor = mqtt_ingest.MqttIngestor(cfg).start(wait=0)
    _ingestors.append(ingestor)
    return ingestor


def stop_ingestors() -> None:
    while _ingestors:
        _ingestors.pop().stop()


_controllers = []                     # every controller of this process, so tests (and shutdown) can stop their feeds


def stop_all() -> None:
    """Stops every demo feed and ingestion subscriber of this process (used when shutting down, and by tests)."""
    for c in _controllers:
        c.stop()
    stop_ingestors()


class FeedController:
    def __init__(self):
        self.feed = None
        _controllers.append(self)

    def start(self, engines: int, motor: bool, interval_s: float, step: int) -> None:
        self.stop()
        cfg = mqtt_config()
        sink = simulator.MqttSink(cfg) if cfg else simulator.LocalSink()
        feeds = simulator.build_feeds(engines, motor)
        self.feed = simulator.LiveFeed(feeds, sink, interval_s, step, reset=True).start()

    def stop(self) -> None:
        if self.feed is not None:
            self.feed.stop()

    def clear(self) -> int:
        """Stops the feed and removes every simulated asset."""
        self.stop()
        if self.feed is not None and self.feed._thread is not None:
            self.feed._thread.join(timeout=5)
        self.feed = None
        return simulator.reset_live_assets()

    def status(self) -> dict:
        if self.feed is None:
            return {"running": False, "done": False, "sent": {}, "total": {}, "errors": 0, "last_error": "", "refused": []}
        return self.feed.status()

    @property
    def running(self) -> bool:
        return self.feed is not None and self.feed.running


def has_live_assets() -> bool:
    return any(a.startswith(simulator.LIVE_PREFIX) for a in db.list_assets()["asset_id"])
