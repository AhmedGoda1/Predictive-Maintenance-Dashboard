# Uploading live data: step by step

Data reaches the dashboard through an **MQTT broker**: your device (or a script that reads your log) *publishes*
readings to the broker, the **ingestion service** picks them up, checks them, stores them and scores the asset, and
the dashboard shows the result.

```
your device / script  ──publish──▶  broker  ──▶  ingestion service  ──▶  database  ──▶  dashboard
```

Part A runs everything on your own computer (about 10 minutes). Part B puts it on the hosted dashboard.
The commands in Part A were run on Linux exactly as written (the macOS and Windows variants were not).

---

## Part A: on your own computer

### 1. Install

```bash
pip install -r requirements.txt
sudo apt install mosquitto mosquitto-clients     # Linux. macOS: brew install mosquitto. Windows: mosquitto.org/download
```

Mosquitto is the broker (the post office) and `mosquitto_pub` / `mosquitto_sub` are command-line tools to send and
watch messages. Any MQTT broker works.

### 2. Create the demo database (optional but recommended)

```bash
python build_db.py
```

This loads the recorded demo assets (21 of them) so the dashboard has something to show next to your data. Skip it and
the dashboard builds it for you on first start. Do it *before* starting the service.

### 3. Start the broker (terminal 1)

```bash
mosquitto -c examples/mosquitto.conf
```

It listens on port 1883 of this computer only, with no password: fine for trying things, not for anything else.
Leave it running.

### 4. Start the ingestion service (terminal 2)

```bash
PDM_MQTT_HOST=localhost python -m pdm.mqtt_ingest
```

You should see `connected to localhost:1883`. Leave it running. (On Windows PowerShell:
`$env:PDM_MQTT_HOST="localhost"; python -m pdm.mqtt_ingest`.)

### 5. Start the dashboard (terminal 3)

```bash
streamlit run dashboard/app.py
```

Open the address it prints. In the sidebar, open **Live data (MQTT)** and tick **Refresh every 3 s** so new readings
appear by themselves. The panel says the app "does not run its own MQTT subscriber": that is right, the ingestion
service from step 4 does that job, and the two share the database.

### 6. See it work with simulated sensors (terminal 4)

```bash
PDM_MQTT_HOST=localhost python scripts/simulate.py --engines 3 --motor --interval 0.5
```

Four assets named `LIVE-...` appear in the fleet table (Source: *live feed*), start as **Learning**, then get a
status, a health index and, for the engines, an estimated remaining life. Press Ctrl-C when you have seen enough.

### 7. Send one asset by hand

An **asset** is one piece of equipment. First say what it is, then send readings.

```bash
mosquitto_pub -t pdm/v1/assets/press4/register -q 1 \
  -m '{"type_id": "brushed_dc_motor", "name": "Press 4 drive", "site": "Plant A"}'

mosquitto_pub -t pdm/v1/assets/press4/readings -q 1 \
  -m '{"ts": "2026-10-06T10:00:00Z", "values": {"voltage_regime": 3, "temp_motor": 41.5, "vib_1x": 0.12, "current": 1.6}}'
```

What this means:
- `press4` is the id you choose (letters, digits, `.` `_` `-`; at most 64 characters).
- `type_id` says what kind of equipment it is, which decides the sensor names you may use. List them with
  `python scripts/publish_csv.py --list-channels brushed_dc_motor` (the other type is `turbofan_engine`).
- `ts` is when it was **measured** (ISO 8601; `Z` means UTC). Each reading needs a *later* time than the one before.
- `values` holds `channel: number`. Send only the sensors you have.
- `voltage_regime` describes the motor's supply (3 = nominal). Send it with the first reading; after that it is
  remembered if you leave it out.

Watch the answers (terminal 5): the service replies on two topics.

```bash
mosquitto_sub -t 'pdm/v1/assets/+/state' -t 'pdm/v1/assets/+/rejected' -v
```

Right now the answer says `"status": "Learning"`. The system must see **20 readings** to learn what *healthy* looks
like for this asset before it can judge it. Send 25 in a loop:

```bash
for i in $(seq 1 25); do
  mosquitto_pub -t pdm/v1/assets/press4/readings -q 1 \
    -m "{\"ts\": \"$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)\", \"values\": {\"temp_motor\": 41.$((i%10)), \"vib_1x\": 0.1$((i%7)), \"current\": 1.6}}"
  sleep 0.05
done
```

The status changes to **Healthy** and `press4` shows in the dashboard.

### 8. Send a CSV file

This is the easiest way to load a log you already have. `examples/motor_log.csv` is a sample with the columns
`time, temp_c, vib_g, vib_hf, current_a, supply_v, rpm`. Your columns will have other names, so you tell the script
which column is which sensor channel:

```bash
PDM_MQTT_HOST=localhost python scripts/publish_csv.py examples/motor_log.csv \
  --asset press5 --type brushed_dc_motor --name "Press 5 drive" \
  --ts-column time \
  --map temp_c=temp_motor --map vib_g=vib_1x --map vib_hf=vib_band_0_4k \
  --map current_a=current --map supply_v=voltage --map rpm=speed_rpm \
  --const voltage_regime=5 \
  --now --batch 10 --interval 0.3
```

- `--map column=channel` for every column you want to send (repeat it). Columns you do not map are ignored.
- `--const channel=value` sends a fixed value with every reading (here the supply regime).
- `--now` shifts the times in the file so the last reading is *now*, which replays an old log as if it had just
  been measured. Leave it out to keep the times in the file.
- `--dry-run` checks the file and the mapping and sends nothing. Try it first.
- A typo is caught before anything is sent: `error: not channels of brushed_dc_motor: temperature. Valid: ...`.
- Without `--now`, running the same file twice is harmless: readings whose time is already stored are ignored as
  duplicates. With `--now` the times change on every run, so send such a file **once** per asset (the service
  refuses a second run as out of order, and tells you so).

`press5` appears as **Warning**: its motor temperature climbs past the 60 °C limit. Click its row in the fleet table
to open it.

### 9. Send from your own device

`examples/device_publisher.py` is what a device does, using nothing but the MQTT library: say what it is once, then
publish a reading every few seconds. Replace `read_sensors()` with code that reads your hardware.

```bash
python examples/device_publisher.py --host localhost --asset press6 --every 2
```

Use QoS 1 (as the example does) so the broker confirms it received each reading.

---

## Part B: on the hosted dashboard

The hosted app can only run the dashboard, so it needs a **broker on the internet** that both it and your device can
reach, and it runs the ingestion service inside itself.

1. **Get a broker** with TLS: a hosted MQTT service (HiveMQ Cloud, EMQX Cloud and others have free tiers) or your own
   Mosquitto on a server. Note its host name and port (usually 8883).
2. **Create credentials**: one user for the dashboard's service and one per device. Restrict each device to its own
   topics (see *Security* in the README for a tested rule set).
3. **Give the hosted app the broker**: in Streamlit's *Manage app* menu, open *Settings → Secrets* and add

   ```toml
   PDM_MQTT_HOST = "your-broker.example.com"
   PDM_MQTT_PORT = "8883"
   PDM_MQTT_USERNAME = "dashboard-service"
   PDM_MQTT_PASSWORD = "..."
   ```

   then reboot the app.
4. **Check**: in the sidebar, *Live data (MQTT)* should say `🟢 connected to your-broker.example.com:8883`.
5. **Send data from your computer** with the same commands as in Part A, adding the broker and your device's
   credentials: `--host your-broker.example.com --port 8883 --username dev-press5 --password ... --tls`
   (`mosquitto_pub` takes `-h`, `-p`, `-u`, `-P` and `--capath /etc/ssl/certs`).

Things to know before you rely on Part B:
- **Not tested here.** I could not try a hosted broker or Streamlit's secrets from this environment. Part A is
  verified, and the same code path with TLS, passwords and per-device permissions was tested against a local
  Mosquitto. Streamlit exposes top-level secrets as environment variables, which is what the app reads: if the
  sidebar does not show *connected*, that is the first thing to check.
- **The hosted app forgets live data when it restarts.** Its database lives on the app's temporary disk, so a
  reboot or redeploy removes the live assets. Fine for a demo; for real use the database must be on persistent
  storage.
- Only one ingestion service should use a given client id (`PDM_MQTT_CLIENT_ID`); do not run the same one on your
  laptop and in the hosted app at the same time.

---

## When something does not work

| You see | Likely cause and fix |
|---|---|
| The asset stays **Learning** | It needs 20 readings. Send more. |
| Nothing appears at all | Is the service running (step 4)? Watch everything with `mosquitto_sub -t 'pdm/v1/#' -v`: if your message shows there, the broker has it; if the service is up you will see a `state` reply. |
| `rejected`: *unknown asset … register it first* | Send the `register` message (step 7) before readings. |
| `rejected`: *unknown channel(s) for …* | A sensor name is not one of the type's channels: `python scripts/publish_csv.py --list-channels TYPE`. |
| `rejected`: *out of order: older than the newest stored reading* | Each reading needs a later `ts` than the previous one. Check clocks, and that you are not re-sending an old file with new asset data. |
| `rejected`: *age is required* | Types measured in cycles (`turbofan_engine`) need `"age": <cycle number>` in every reading (`--age-column` in the CSV script). |
| `rejected`: *voltage_regime is required for the first reading* | The motor's first reading must say which supply it runs on. |
| `duplicates` in the reply | That time was already stored. Harmless: it is what a retry looks like. |
| *Connection refused* / *Not authorized* | Broker not running or wrong host/port, or wrong user/password. With TLS add `--tls`. |
| Dashboard does not update | Tick *Refresh every 3 s* in the sidebar, or reload the page. |
| Your equipment is neither a motor nor an engine | Describe it once in `pdm/registry.py` (its sensor names and units); see *Adding a new kind of equipment* in the README. Nothing else changes. |

## What the status means

- **Healthy / Warning / Critical** come from a health index (0-100) that compares the asset's sensors with how *this
  asset* looked at the start, plus hard limits (e.g. motor temperature 60 / 70 °C). A change must hold for 3
  readings before it counts.
- **Failed** only appears when you tell the system: publish to `pdm/v1/assets/<id>/failure` with
  `{"ts": "...", "mode": "bearing"}`. It is stored as a failure label; nothing retrains a model from it yet.
- **Estimated RUL** (remaining useful life) exists only for equipment types with a validated model (turbofan
  engines). For the motor you get the health index and status, not a number of minutes.
