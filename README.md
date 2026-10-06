# Predictive Maintenance Dashboard

IoT group project: a predictive-maintenance dashboard for a brushed DC motor, built on an open
run-to-failure dataset.

**Live dashboard:** https://predictive-maintenance-dashboard-3ldxwrb9s9av4egmvykm9k.streamlit.app

## Pipeline

```
data/*.xlsx  ──ingest.py──▶  SQLite (maintenance.db)  ──health.py──▶  health scores, alerts, RUL
                                      │                                      │
                                      └──────────── dashboard/app.py ◀───────┘   (replayed as a live stream)
```

| File | Purpose |
|---|---|
| `schema.sql` | Tables: `machines`, `sensor_readings`, `health_scores`, `maintenance_alerts`, `model_metrics` |
| `db_manager.py` | SQLite access (single and bulk inserts, queries returning DataFrames) |
| `ingest.py` | Loads the dataset workbook, derives supply regime, failure flag and true RUL |
| `health.py` | Health index, status, alert generation, RUL estimate and its evaluation |
| `build_db.py` | Runs ingest + analysis and writes `maintenance.db` |
| `dashboard/` | Streamlit app (reads the database; builds it on first start if missing) |
| `tests/` | pytest suite (`python -m pytest`) |

## Run it

```bash
pip install -r requirements.txt
python build_db.py                 # optional: the dashboard builds the database itself if it is missing
streamlit run dashboard/app.py
python -m pytest
```

## Dataset

*F.A.I.R. open dataset of brushed DC motor faults for testing of AI algorithms*,
https://zenodo.org/records/4314249, licence **CC-BY-4.0** (credit the dataset authors listed on the
Zenodo page when you publish).

- One cheap brushed DC motor was monitored (vibration, current, voltage, temperature) until it failed.
- `data/open_DC_motor-processing_data.xlsx` is the dataset's processing sheet: one row per raw HDF5
  recording (377 rows, about 35 minutes, one row every ~4.4 s). `data/file_phases.csv` maps each row to the
  folder (operating phase) of its raw file.
- The run has four phases: `01-Start 3V`, `02-Change 5V`, `03-Re_start 3V`, `04-Change 5V`. 3 V is the
  nominal supply; 5 V is overstress that speeds up wear. The motor stops at 18:00:30, and that last event
  gives a real time-to-failure label.
- The raw waveforms (about 480 MB) are not in the repository and are not needed by the pipeline.

## Method

- **Health index (0-100):** vibration at the 1x harmonic and in the 0-4 kHz and 4-8 kHz bands is compared with
  a healthy baseline, taken from the first 20 readings of the same supply regime (the regime changes the
  vibration level on its own). Larger deviation means a lower score.
- **Status:** Healthy ≥ 70, Warning ≥ 40, Critical below; also Warning ≥ 60 °C and Critical ≥ 70 °C motor
  temperature. A change must hold for 3 readings. "Failed" once the motor has stopped.
- **Alerts:** one alert each time the status gets worse, naming the feature driving the deviation, with a
  suggested action.
- **RUL estimate:** random forest on smoothed sensor features plus accumulated time at 5 V.

### Results and limits (be upfront about these in the report)

Mean absolute error of the RUL estimate on the 375 readings before failure:

| Evaluation | Model | Predict the training mean |
|---|---|---|
| Blocked cross-validation (blocks of 30 readings, neighbours left out) | ~346 s | ~585 s |
| Forward in time (train on first 75 %, test on last 25 %) | ~796 s | ~1251 s |

- The dataset contains **one motor run**. Everything is evaluated on that single run, so the RUL estimate is
  indicative only and says nothing about other motors.
- The forward-in-time error is more than twice the cross-validated one, which is the honest picture of
  predicting the future of a run the model has not seen.
- Sensors alone barely beat a constant guess; the accumulated overstress time carries most of the signal.
- The dashboard replays the recorded run as a live stream. The actual time to failure is shown next to the
  estimate only so the two can be compared.

## Ideas for further work

- Add features from the raw HDF5 waveforms (RMS, kurtosis, spectra) and more of the 10 harmonics.
- Tune the status thresholds and compare other anomaly detectors on the same baseline.
- Use more motors or runs, if available, to test generalization.
