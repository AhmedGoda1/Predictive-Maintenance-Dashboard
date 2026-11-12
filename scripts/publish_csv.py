"""Publishes the rows of a CSV file to the ingestion service, as live readings of one asset.

Each row becomes one reading. You say which column holds the time and which columns are which sensor channel
of the asset type (`python scripts/publish_csv.py --list-channels brushed_dc_motor` shows the valid names).

Example: a motor log with columns  time, temp_c, vib_g, supply_v
  python scripts/publish_csv.py log.csv --asset press4 --type brushed_dc_motor --name "Press 4 drive" \\
      --ts-column time --map temp_c=temp_motor --map vib_g=vib_1x --map supply_v=voltage \\
      --const voltage_regime=3 --host broker.example.com --username dev-press4 --password secret --tls

  --now        shift the times in the file so that its last reading is at the current time (replays an old log as if it
               had just been measured; the spacing between readings is kept)
  --interval   seconds to wait between batches, to feed the dashboard gradually (default 0: as fast as possible)
  Times without a time zone in the file are taken as UTC.
  Exit codes: 0 stored and scored; 1 the service refused part of the data; 2 bad input or no broker; 3 no (or too few)
  answers from the ingestion service.
  --age-column column with the age of the asset (required for types measured in cycles, e.g. turbofan_engine)
Broker settings come from the options or the PDM_MQTT_* environment variables.
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pdm import mqtt_ingest, registry, simulator  # noqa: E402


def parse_pairs(items, what: str) -> dict:
    out = {}
    for item in items or []:
        if "=" not in item:
            raise SystemExit(f"{what} must look like name=value, got {item!r}")
        key, value = item.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def build_readings(df: pd.DataFrame, type_id: str, ts_column: str, mapping: dict, consts: dict = None,
                   age_column: str = None, now: bool = False) -> list:
    """The rows of `df` as readings: {"ts", "age"?, "values": {channel: number}}. Raises ValueError when it cannot."""
    t = registry.get_type(type_id)
    valid = {c.name for c in t.channels}
    bad = sorted((set(mapping.values()) | set(consts or {})) - valid)
    if bad:
        raise ValueError(f"not channels of {type_id}: {', '.join(bad)}. Valid: {', '.join(sorted(valid))}")
    missing = [c for c in [ts_column, age_column, *mapping] if c and c not in df.columns]
    if missing:
        raise ValueError(f"column(s) not in the file: {', '.join(missing)}. The file has: {', '.join(map(str, df.columns))}")
    if not mapping:
        raise ValueError("map at least one column to a channel with --map column=channel")
    if t.age_unit != "s" and not age_column:
        raise ValueError(f"{type_id} is measured in {t.age_unit}s: give --age-column")
    if df.empty:
        raise ValueError("the file has no data rows")
    consts = {k: float(v) for k, v in (consts or {}).items()}

    ts = pd.to_datetime(df[ts_column], errors="coerce", utc=True)
    if ts.isna().any():
        raise ValueError(f"{int(ts.isna().sum())} value(s) in column {ts_column!r} are not valid timestamps")
    if now:                                              # keep the spacing, shift the log so that its last reading is now
        ts = ts + (pd.Timestamp.now(tz="UTC") - ts.max())
    readings = []
    for i, (_, row) in enumerate(df.iterrows()):
        values = dict(consts)
        for column, channel in mapping.items():
            v = pd.to_numeric(row[column], errors="coerce")
            if pd.notna(v) and np.isfinite(v):
                values[channel] = float(v)
        reading = {"ts": ts.iloc[i].isoformat(), "values": values}
        if age_column:
            age = pd.to_numeric(row[age_column], errors="coerce")
            if pd.isna(age) or not np.isfinite(age):
                raise ValueError(f"row {i + 2}: {age_column!r} is not a number")
            reading["age"] = float(age)
        readings.append(reading)
    return readings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="?", help="the CSV file (with a header row)")
    ap.add_argument("--list-channels", metavar="TYPE", help="show the channels of an asset type and exit")
    ap.add_argument("--asset", help="asset id: letters, digits, . _ - (at most 64)")
    ap.add_argument("--type", dest="type_id", help="asset type, e.g. brushed_dc_motor or turbofan_engine")
    ap.add_argument("--name", help="display name of the asset")
    ap.add_argument("--site", help="where the asset is")
    ap.add_argument("--ts-column", help="column with the time of each measurement")
    ap.add_argument("--age-column", help="column with the asset's age (cycles or seconds since start)")
    ap.add_argument("--map", action="append", metavar="COLUMN=CHANNEL", help="map a column to a sensor channel (repeatable)")
    ap.add_argument("--const", action="append", metavar="CHANNEL=VALUE", help="a fixed value sent with every reading, e.g. voltage_regime=3")
    ap.add_argument("--now", action="store_true", help="shift the times so the last reading is at the current time")
    ap.add_argument("--batch", type=int, default=50, help="readings per message (default 50)")
    ap.add_argument("--reply-timeout", type=float, default=15.0, help="seconds to wait for the service's answers (default 15)")
    ap.add_argument("--interval", type=float, default=0.0, help="seconds between messages (default 0)")
    ap.add_argument("--no-register", action="store_true", help="do not send the register message (asset already exists)")
    ap.add_argument("--dry-run", action="store_true", help="check the file and the mapping, publish nothing")
    ap.add_argument("--host"), ap.add_argument("--port", type=int), ap.add_argument("--username"), ap.add_argument("--password")
    ap.add_argument("--tls", action="store_true", help="use TLS (default on for port 8883)")
    args = ap.parse_args(argv)

    if args.list_channels:
        try:
            t = registry.get_type(args.list_channels)
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            return 2
        print(f"{t.type_id} ({t.name}); age is counted in {'seconds' if t.age_unit == 's' else t.age_unit + 's'}")
        for c in t.channels:
            print(f"  {c.name:<18} {c.kind:<10} {c.unit:<8} {c.description}")
        return 0
    if args.batch < 1:
        ap.error("--batch must be at least 1")
    for needed in ("csv", "asset", "type_id", "ts_column"):
        if not getattr(args, needed):
            ap.error(f"{needed.replace('_', '-')} is required (or use --list-channels TYPE)")

    try:
        df = pd.read_csv(args.csv)
        readings = build_readings(df, args.type_id, args.ts_column, parse_pairs(args.map, "--map"),
                                  parse_pairs(args.const, "--const"), args.age_column, args.now)
    except (ValueError, KeyError, FileNotFoundError, pd.errors.ParserError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"{len(readings)} reading(s) of asset {args.asset!r} ({args.type_id}); first: {readings[0]}")
    if args.dry_run:
        return 0

    cfg = mqtt_ingest.config_from_options(args.host, args.port, args.username, args.password, args.tls)
    if cfg is None:
        print("error: no broker given: use --host or PDM_MQTT_HOST", file=sys.stderr)
        return 2
    try:
        sink = simulator.MqttSink(cfg)
    except (ConnectionError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    try:
        before = sink.replies[args.asset]                  # answers heard so far; the ones to this upload come after
        messages = 0
        if not args.no_register:
            meta = {"type_id": args.type_id, "name": args.name or args.asset, "site": args.site, "metadata": {"live": True}}
            sink.publish(args.asset, "register", {k: v for k, v in meta.items() if v is not None})
            messages += 1
        for i in range(0, len(readings), args.batch):
            sink.publish(args.asset, "readings", {"readings": readings[i:i + args.batch]})
            messages += 1
            print(f"sent {min(i + args.batch, len(readings))}/{len(readings)}", flush=True)
            if args.interval and i + args.batch < len(readings):
                time.sleep(args.interval)
        # The broker has the messages. Now find out what the ingestion service made of them.
        heard = sink.wait_for_replies(args.asset, messages, since=before, timeout=args.reply_timeout)
        if sink.rejections:
            print("the service refused part of the data:")
            for t, payload in list(sink.rejections)[-5:]:
                print(f"  {t}: {payload}")
            return 1
        if heard == 0:
            print(f"warning: the broker accepted the data but the ingestion service did not answer within "
                  f"{args.reply_timeout:g} s. Is it running (python -m pdm.mqtt_ingest)? A service that is not "
                  f"connected, and has no saved session on the broker, never sees these messages.", file=sys.stderr)
            return 3
        if heard < messages:
            print(f"warning: only {heard} of {messages} messages were answered within {args.reply_timeout:g} s; "
                  f"the service may still be working through them.", file=sys.stderr)
            return 3
    finally:
        sink.close()
    print("done: the ingestion service has stored and scored the data. Open the dashboard: the asset is scored once "
          "it has 20 readings (until then it is 'Learning').")
    return 0


if __name__ == "__main__":
    sys.exit(main())
