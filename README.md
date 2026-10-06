# Predictive Maintenance Dashboard

IoT group project: a predictive-maintenance system that turns sensor data from any registered type of
equipment into a health index, alerts and a remaining-useful-life (RUL) estimate with a prediction
interval, and shows them in a dashboard.

**Live dashboard:** https://predictive-maintenance-dashboard-3ldxwrb9s9av4egmvykm9k.streamlit.app

## Architecture

```
devices / gateways ──MQTT──▶ broker ──▶ ingestion service ──▶ asset-agnostic SQLite ──▶ dashboard
(or scripts/simulate.py)    (TLS, ACLs)  validate · store ·     assets / readings /       fleet + asset views
                                         score · alert          measurements (long)
                                         ▲                       ▲
                                         │ health index (layer A), learned RUL model (layer C)
dataset adapters (motor, C-MAPSS) ───────┴─ the same code scores recorded runs offline
```

| Path | Purpose |
|---|---|
| `pdm/registry.py` | Asset types: channels, units, which channels feed the health index, limits, RUL thresholds |
| `pdm/schema.sql`, `pdm/db.py` | Asset-agnostic schema and access layer (`assets`, `readings`, `measurements`, `failure_events`, `health_scores`, `maintenance_alerts`, `models`, `metrics`) |
| `pdm/ingest.py` | **Transport-independent ingestion**: validation, idempotent storage, scoring on arrival |
| `pdm/mqtt_ingest.py` | **MQTT ingestion service** (`python -m pdm.mqtt_ingest`) |
| `pdm/simulator.py`, `scripts/simulate.py` | Simulated sensors that publish recorded runs as live data |
| `pdm/datasets/` | Adapters turning a source dataset into the common `Run` format: `motor.py`, `cmapss.py` |
| `pdm/health.py` | Health index, status and alerts for any registered asset type |
| `pdm/rul.py` | Learned RUL model (fleet-level, prediction interval), evaluation, single-run fallback |
| `pdm/train.py` | Trains and evaluates the RUL model on the C-MAPSS subsets |
| `pdm/pipeline.py`, `build_db.py` | Builds `maintenance.db` with the recorded demo assets |
| `dashboard/` | Streamlit app: fleet overview, asset detail, live demo feed (builds the database on first start if missing) |
| `tests/` | pytest suite, including integration tests against a real MQTT broker |

## Run it

```bash
pip install -r requirements.txt
python build_db.py                      # builds maintenance.db (the dashboard does this itself if it is missing)
streamlit run dashboard/app.py
python -m pytest                        # the MQTT tests need a broker: mosquitto on the PATH, or pip install amqtt

python scripts/fetch_cmapss.py          # optional: all four C-MAPSS subsets (only FD001 is in the repo)
python -m pdm.train                     # optional: retrain / re-evaluate the RUL model on every available subset
```

## Dashboard

- **Fleet overview:** every asset, ranked by maintenance priority (worst status first, then shortest estimated
  remaining life). Status counts, a priority table (click a row to open the asset), health index by asset,
  RUL with its 80 % interval, open alerts, and a Models & data tab with the model registry and the C-MAPSS
  validation table. A filter row sets the asset type and a *snapshot* slider that replays the whole fleet
  through its recorded life.
- **Asset detail:** KPIs, health timeline, RUL estimate vs. actual with the interval band, any sensor of the
  asset type (with its limits and overstress periods), alert log with work-order buttons, and how the numbers
  were produced and how far to trust them. It has its own play / pause / position replay.
- RUL is never drawn on a shared axis across asset types, because the units differ (cycles vs. minutes);
  the fleet view draws one RUL chart per type. Status colours always come with an icon and a label.
- A new asset type appears in both views once it is registered; no dashboard code changes.

## Live ingestion (MQTT)

Devices or a gateway publish to an MQTT broker; the ingestion service subscribes, validates, stores and scores,
and the dashboard shows the result. No real equipment is connected in this project, so `scripts/simulate.py`
publishes recorded runs as if the assets were being measured right now. Everything after the broker is the real
path.

**New to this? Follow the step-by-step tutorial: [docs/LIVE_DATA.md](docs/LIVE_DATA.md)** (broker, service, a CSV
file, your own device, the hosted dashboard, troubleshooting). `scripts/publish_csv.py` sends a CSV log mapped to
sensor channels; `examples/device_publisher.py` shows what a device does.

```bash
mosquitto -c examples/mosquitto.conf                          # any MQTT broker (Mosquitto, EMQX, HiveMQ, ...)
PDM_MQTT_HOST=localhost python -m pdm.mqtt_ingest             # the ingestion service
PDM_MQTT_HOST=localhost python scripts/simulate.py --engines 3 --motor     # simulated sensors
streamlit run dashboard/app.py                                # watch the fleet change
```

**Topics** (JSON payloads; `<id>` = letters, digits, `.` `_` `-`, at most 64 characters):

| Topic | Direction | Payload |
|---|---|---|
| `pdm/v1/assets/<id>/register` | in | `{"type_id": "turbofan_engine", "name": "...", "site": "...", "source": "...", "metadata": {}}` (known types: see `pdm/registry.py`) |
| `pdm/v1/assets/<id>/readings` | in | one reading `{"ts": "2024-05-01T12:00:00Z", "age": 31, "values": {"s2": 642.1}}`, or `{"readings": [...]}` or a list (at most 1000) |
| `pdm/v1/assets/<id>/failure` | in | `{"ts": "...", "age": 148, "mode": "HPC"}`: a maintenance outcome, used as the failure label |
| `pdm/v1/assets/<id>/state` | out, retained | the asset's current status, health index and RUL estimate, and the counts of the last message |
| `pdm/v1/assets/<id>/rejected` | out | what was refused and why |
| `pdm/v1/service/status` | out, retained | `online` / `offline` (the last will of the service) |

```bash
mosquitto_pub -t pdm/v1/assets/press4/register -q 1 -m '{"type_id": "brushed_dc_motor", "name": "Press 4 drive"}'
mosquitto_pub -t pdm/v1/assets/press4/readings -q 1 -m '{"ts": "2026-10-06T10:00:00Z", "values": {"voltage_regime": 3, "temp_motor": 41.5, "vib_1x": 0.12}}'
mosquitto_sub -t 'pdm/v1/assets/+/state' -t 'pdm/v1/assets/+/rejected' -v
```

**What the service guarantees**
- A reading must name channels of the asset's type, with finite numbers. A bad reading is refused with a reason
  on `rejected`; the good ones in the same message are kept.
- Delivery is at-least-once: QoS 1, a persistent session (fixed client id), and acknowledgement to the broker only
  after the message is stored and scored. If the service is down, the broker keeps the messages. Re-sending a
  reading (same timestamp) is a harmless duplicate, so redelivery never double-counts.
- A reading older than the newest stored one is refused (out of order); `age` must increase. `age` is optional for
  second-based types (derived from `ts`) and required for the others (e.g. engine cycles). A missing operating
  condition (e.g. the motor's `voltage_regime`) carries forward the last known value.
- An asset is scored once it has enough readings to learn its healthy baseline (20); until then it is
  reported as *Learning*. After that every batch re-scores the asset with the same code as the offline pipeline:
  health index, status, the learned RUL model when one is registered for the type, and alerts (appended once,
  never re-created, so their ids stay stable).
- A bad message never stops the service; an error while scoring is reported and the data is kept.

**Security.** Run the broker with TLS and give every client its own credentials. This ACL was tested against
Mosquitto (`tests/test_mqtt_security.py`): a device can publish only its own inbound topics and read only its own
answers, and cannot forge the service's `state` / `rejected` messages.

```
user pdm-service
topic read  pdm/v1/assets/+/register
topic read  pdm/v1/assets/+/readings
topic read  pdm/v1/assets/+/failure
topic write pdm/v1/assets/+/state
topic write pdm/v1/assets/+/rejected
topic write pdm/v1/service/status

user dev-press4                       # one such block per device
topic write pdm/v1/assets/press4/register
topic write pdm/v1/assets/press4/readings
topic write pdm/v1/assets/press4/failure
topic read  pdm/v1/assets/press4/state
topic read  pdm/v1/assets/press4/rejected
```

Client settings come from environment variables: `PDM_MQTT_HOST`, `PDM_MQTT_PORT` (default 1883), `PDM_MQTT_USERNAME`,
`PDM_MQTT_PASSWORD`, `PDM_MQTT_TLS` (default on for port 8883), `PDM_MQTT_CA_CERTS`, `PDM_MQTT_CLIENT_ID`.
Use one subscriber per client id: two with the same id take the broker session from each other. Two subscribers with
different ids (e.g. a standalone service and an app that runs its own) both receive every message; that is safe, because
the database keeps one reading per asset and time, but it doubles the work.

**The hosted dashboard.** Streamlit Cloud can only run the dashboard, so when `PDM_MQTT_HOST` (and the other
variables, as app secrets) point at a broker the app reaches, it runs the ingestion subscriber itself, and its
"Live demo feed" publishes to that broker. Anyone can then publish to the same topics, e.g. `scripts/simulate.py`
from a laptop, and the hosted fleet view updates. Without a broker the demo feed writes straight into the ingestion
code and the sidebar says so.

**Limits of this MVP**
- One subscriber processes messages in order, one at a time. Measured on a laptop-class CPU: about 10 messages per
  second (80-100 ms each, mostly scoring the asset's history). The cost is per message, not per reading, so a
  device that sends batches of readings is far cheaper than one that sends them one by one. To scale out, run one
  subscriber per group of assets (separate client ids and topic filters).
- Every batch re-scores the asset's whole history. That is fine for hundreds of readings per asset; for long
  histories, score a window and keep the baseline.
- The healthy baseline of an operating regime is provisional until the regime has 20 readings, so statuses of its
  first readings can still change.
- SQLite on one machine. A production deployment would use a server database (PostgreSQL / TimescaleDB) with the
  same schema.
- Tested against Mosquitto, including TLS with a self-signed certificate, passwords and ACLs; also against the pure
  Python `amqtt` broker, which cannot test offline queuing. Not tested: a hosted broker service, broker clustering.

## Adding a new kind of equipment

1. Register an `AssetType` in `pdm/registry.py`: its channels with units, which are operating conditions,
   which feed the health index and how (`log_ratio_up` for growing amplitudes, `z_abs` for either direction),
   any hard limits, and the status thresholds.
2. Write an adapter in `pdm/datasets/` that returns `Run` objects (a wide time series plus the failure time
   when known). In production the same tables are filled by an ingestion service instead of an adapter.
3. Storage, health index, alerts and the RUL model need no code changes. New sensors need no schema change,
   because measurements are stored in long format.

## Three levels of RUL, depending on what data exists

| Level | Needs | Status in this repo |
|---|---|---|
| A. Health index vs. the asset's own healthy baseline | no failures | implemented for every asset type |
| B. Degradation-trend extrapolation | a few failures or an engineering threshold | not implemented |
| C. Learned RUL model across a fleet | dozens of run-to-failure assets | implemented (`pdm/rul.py`), validated on C-MAPSS |

The system should report which level produced a number. `health_scores.method` stores it: `learned` or
`single_run_experimental`.

## Learned RUL model (level C)

- **Features** (causal: a reading never uses later readings): per sensor, a short and a long rolling mean, a
  rolling standard deviation and the change over one window, all z-scored within the operating regime, plus age.
  Regimes are found with k-means on the operating settings; sensors that never vary are dropped.
- **Target:** `min(RUL, cap)` with a 125-cycle cap (piecewise-linear RUL), because the exact remaining life of
  a healthy engine cannot be read from its sensors.
- **Model:** gradient boosting for the estimate plus two quantile models for the 10 % / 90 % bounds. The
  interval width is corrected with residuals of engines the models did not see during fitting (conformalised
  quantile regression, 80 % nominal coverage).
- **Evaluation:** the standard C-MAPSS protocol. Fit on the train engines, then predict the remaining life at
  the last reading of every held-out test engine and compare with the true RUL from the benchmark. No
  hyper-parameter search was done against the test engines.

### Results (held-out test engines, RUL in cycles)

| Subset | Conditions / fault modes | Train / test engines | RMSE | MAE | NASA score | Interval coverage (nominal 80 %) | Constant guess RMSE | Age-only RMSE |
|---|---|---|---|---|---|---|---|---|
| FD001 | 1 / 1 | 100 / 100 | **14.5** | 10.9 | 314 | 0.80 | 43.1 | 32.1 |
| FD002 | 6 / 1 | 260 / 259 | **25.8** | 17.1 | 8216 | 0.81 | 54.1 | 38.2 |
| FD003 | 1 / 2 | 100 / 100 | **13.7** | 9.7 | 322 | 0.69 | 45.1 | 35.3 |
| FD004 | 6 / 2 | 249 / 248 | **25.6** | 18.2 | 4378 | 0.80 | 54.9 | 47.8 |

The NASA score penalises late predictions harder than early ones (lower is better). Full numbers are in
`models/cmapss_metrics.json`.

Read these with the following in mind:
- **Coverage:** an interval whose upper bound reaches the cap counts as covering any longer true life ("at
  least 125 cycles"). Counted strictly, coverage is 0.69 / 0.61 / 0.57 / 0.54. FD003 is under-covered even by
  the cap-aware count (0.69 against 0.80), so its intervals are too narrow.
- Operating-condition normalisation matters: the six-condition subsets (FD002, FD004) are clearly harder.
- The models are gradient-boosted trees on hand-made window features. Sequence models (LSTM, CNN,
  transformer) are the obvious next candidate and were not tried.
- Generalisation is shown across engines of one type (including different operating conditions and fault
  modes). It is **not** shown across asset types: the turbofan model says nothing about the motor.

## The DC-motor asset (one run to failure)

*F.A.I.R. open dataset of brushed DC motor faults for testing of AI algorithms*, https://zenodo.org/records/4314249,
licence **CC-BY-4.0**. Reñones, A. (2020), CARTIF, DOI 10.5281/zenodo.4314249.

- One cheap brushed DC motor was monitored (vibration, current, voltage, temperature) until it failed.
  `data/open_DC_motor-processing_data.xlsx` has one row per raw recording (377 rows, about 35 minutes);
  `data/file_phases.csv` maps each row to its operating phase.
- The run has four phases: 3 V (nominal) and 5 V (overstress), `01-Start 3V`, `02-Change 5V`, `03-Re_start 3V`,
  `04-Change 5V`. The motor stops at 18:00:30. There is an 8-minute pause between phases 02 and 03.
- Health index: vibration at the 1x harmonic and in the 0-4 kHz and 4-8 kHz bands against a healthy baseline of
  the same supply regime. Status: Healthy ≥ 70, Warning ≥ 40, Critical below, plus a motor-temperature limit.
- RUL: with a single run there is nothing to validate across assets, so the estimate is marked experimental.
  Mean absolute error 331 s (blocked cross-validation) and 772 s (forward in time), against 585 s and 1251 s
  for always predicting the training mean. Most of its signal is accumulated time at 5 V. Use it as a demo, not
  as evidence.
- The raw waveforms (about 480 MB) are not in the repository and are not needed by the pipeline.

## Turbofan fleet (NASA C-MAPSS)

A. Saxena and K. Goebel (2008), *Turbofan Engine Degradation Simulation Data Set*, NASA Ames Prognostics Data
Repository (public domain). A. Saxena et al., "Damage Propagation Modeling for Aircraft Engine Run-to-Failure
Simulation", PHM 2008. One cycle is mapped to one hour on a synthetic timeline.

`build_db.py` loads 20 FD001 *test* engines. They are scored by the model trained on the FD001 train engines
only, so the predictions are out-of-sample. At their last reading, the remaining life of Critical engines was
8-21 cycles (mean 14), of Warning engines 38-57 (mean 47) and of Healthy ones 84-137 (mean 107). Only the FD001 files and the FD001 model are committed.

## What is still missing for a commercial product

- Level B (trend extrapolation) for assets with too few failures for level C.
- Survival-style handling of assets that have not failed yet, and domain adaptation / fine-tuning on a customer's
  few failures.
- Model versioning with drift monitoring and a retraining loop fed by maintenance outcomes.
- Dashboard login, multi-tenancy and CMMS integration (broker-level authentication and per-device ACLs exist).
