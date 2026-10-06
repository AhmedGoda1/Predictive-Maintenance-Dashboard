"""Streams simulated sensor readings into the system, as live data would arrive.

By default readings are PUBLISHED TO AN MQTT BROKER, the way a device or gateway would send them; the
ingestion service (python -m pdm.mqtt_ingest) picks them up from there. Broker settings come from the
PDM_MQTT_* environment variables or the options below.

Examples
  PDM_MQTT_HOST=localhost python scripts/simulate.py                       # 4 engines through the broker
  python scripts/simulate.py --host broker.example.com --port 8883 --username sim --password secret --tls
  python scripts/simulate.py --motor --engines 2 --interval 0.5
  python scripts/simulate.py --direct                                      # no broker: straight into the local database

Press Ctrl-C to stop. Open the dashboard in another terminal to watch the fleet change.
"""
import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pdm import db, mqtt_ingest, simulator  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", help="MQTT broker host (default: PDM_MQTT_HOST)")
    ap.add_argument("--port", type=int, help="broker port (default: PDM_MQTT_PORT or 1883)")
    ap.add_argument("--username", help="broker user name (default: PDM_MQTT_USERNAME)")
    ap.add_argument("--password", help="broker password (default: PDM_MQTT_PASSWORD)")
    ap.add_argument("--tls", action="store_true", help="use TLS (default on for port 8883)")
    ap.add_argument("--direct", action="store_true", help="skip MQTT and write into the local database directly")
    ap.add_argument("--engines", type=int, default=4, help="number of turbofan engines to stream (default 4)")
    ap.add_argument("--motor", action="store_true", help="also stream the brushed DC motor run")
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between sends (default 1)")
    ap.add_argument("--step", type=int, default=1, help="readings per asset per send (default 1)")
    ap.add_argument("--keep", action="store_true", help="(direct mode) keep earlier simulated assets")
    args = ap.parse_args()

    feeds = simulator.build_feeds(args.engines, args.motor)
    if args.direct:
        if not db.DB_NAME.exists():
            db.init_db()
        sink, target = simulator.LocalSink(), str(db.DB_NAME)
    else:
        env = dict(os.environ)
        if args.host:
            env["PDM_MQTT_HOST"] = args.host
        for flag, var in [(args.port, "PDM_MQTT_PORT"), (args.username, "PDM_MQTT_USERNAME"), (args.password, "PDM_MQTT_PASSWORD")]:
            if flag:
                env[var] = str(flag)
        if args.tls:
            env["PDM_MQTT_TLS"] = "true"
        cfg = mqtt_ingest.MqttConfig.from_env(env)
        if cfg is None:
            sys.exit("No broker given: use --host or PDM_MQTT_HOST (or --direct for no MQTT).")
        sink, target = simulator.MqttSink(cfg), f"mqtt://{cfg.host}:{cfg.port}"
    feed = simulator.LiveFeed(feeds, sink, args.interval, args.step, reset=not args.keep).start()
    print(f"Streaming {len(feeds)} asset(s) to {target} every {args.interval:g}s. Ctrl-C to stop.")
    try:
        while feed.running:
            time.sleep(2)
            st = feed.status()
            line = "  ".join(f"{a.replace(simulator.LIVE_PREFIX, '')}: {st['sent'][a]}/{st['total'][a]}" for a in st["sent"])
            print(line + (f"   errors: {st['errors']} ({st['last_error']})" if st["errors"] else "")
                  + (f"   refused: {st['refused'][-1][1]}" if st["refused"] else ""), flush=True)
    except KeyboardInterrupt:
        feed.stop()
        print("stopped")
    else:
        print("all recordings sent")
