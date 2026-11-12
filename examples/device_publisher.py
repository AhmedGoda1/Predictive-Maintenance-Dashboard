"""What a device (or a gateway next to it) does, with nothing but the MQTT library. pip install paho-mqtt

Reads its sensors every few seconds and publishes one reading to the ingestion service's topic.
Replace read_sensors() with real code; everything else can stay as it is.

  python examples/device_publisher.py --host localhost --asset press4 --count 25
"""
import argparse
import json
import random
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt


def read_sensors() -> dict:
    """Return {channel: number} using the channel names of the asset type (python scripts/publish_csv.py --list-channels TYPE)."""
    return {"temp_motor": 40 + random.random() * 2, "vib_1x": 0.1 + random.random() * 0.02,
            "current": 1.6 + random.random() * 0.1, "voltage_regime": 3}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--username")
    ap.add_argument("--password")
    ap.add_argument("--tls", action="store_true")
    ap.add_argument("--asset", default="press4")
    ap.add_argument("--type", default="brushed_dc_motor")
    ap.add_argument("--every", type=float, default=2.0, help="seconds between readings")
    ap.add_argument("--count", type=int, default=0, help="stop after this many readings (0 = run until Ctrl-C)")
    args = ap.parse_args()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"device-{args.asset}")
    if args.username:
        client.username_pw_set(args.username, args.password)
    if args.tls:
        client.tls_set()
    client.connect(args.host, args.port)
    client.loop_start()

    base = f"pdm/v1/assets/{args.asset}"
    # say what this asset is (safe to repeat: registering an existing asset changes nothing)
    client.publish(f"{base}/register", json.dumps({"type_id": args.type, "name": args.asset}), qos=1).wait_for_publish()

    sent = 0
    try:
        while not args.count or sent < args.count:
            reading = {"ts": datetime.now(timezone.utc).isoformat(), "values": read_sensors()}
            client.publish(f"{base}/readings", json.dumps(reading), qos=1).wait_for_publish()   # QoS 1: the broker confirms
            sent += 1
            print(f"sent reading {sent}", flush=True)
            time.sleep(args.every)
    except KeyboardInterrupt:
        pass
    client.loop_stop()
    client.disconnect()
