"""Data layer for the dashboard: reads assets, readings, health scores and alerts from SQLite."""
import sys
from pathlib import Path

import pandas as pd

# The package lives in the repository root, one level above this folder.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pdm import db, pipeline  # noqa: E402

MACHINE_ID = "MTR_01"

# model-metric names stored by the pipeline -> names the motor view uses
_MOTOR_METRICS = {
    "rul_mae_blocked_cv": "rul_mae_blocked_cv_s",
    "rul_mae_forward": "rul_mae_forward_s",
    "rul_mae_mean_baseline": "rul_mae_mean_baseline_s",
    "rul_mae_mean_baseline_forward": "rul_mae_mean_baseline_forward_s",
}


def ensure_db() -> None:
    """Builds the database from the committed datasets when it does not exist yet
    (e.g. on a fresh deployment, since maintenance.db is not committed)."""
    if not db.DB_NAME.exists():
        pipeline.build()


def load_machine_data(machine_id: str = MACHINE_ID):
    """Returns (machine, readings joined with health scores, alerts, model metrics) for one motor."""
    ensure_db()
    asset = db.get_asset(machine_id)
    machine = pd.Series({"name": asset["name"], "location": asset["metadata"].get("location", "")}, name=machine_id)

    series = db.get_series(machine_id).rename(columns={"ts": "timestamp"})
    series["regime"] = series["voltage_regime"].map(lambda v: f"{v:g}V")
    segments = db.get_segments(machine_id)
    series["phase"] = None
    for _, seg in segments.iterrows():
        series.loc[series["timestamp"].between(seg["start_ts"], seg["end_ts"]), "phase"] = seg["name"]

    health = db.get_health(machine_id).rename(columns={"ts": "timestamp"})
    health = health[["timestamp", "drift", "health_score", "status", "top_driver", "rul_pred"]]
    data = series.merge(health, on="timestamp", how="left").rename(columns={"rul_pred": "rul_pred_s"})

    failure = db.get_failure(machine_id)
    data["rul_true_s"] = (failure["age"] - data["age"]).clip(lower=0) if failure else float("nan")

    alerts = db.get_alerts(machine_id).rename(columns={"ts": "timestamp"})
    metrics = {_MOTOR_METRICS[k]: v for k, v in db.get_metrics(machine_id).items() if k in _MOTOR_METRICS}
    return machine, data, alerts, metrics


def format_duration(seconds) -> str:
    """Seconds -> '12 min 05 s'."""
    if pd.isna(seconds):
        return "n/a"
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60} min {seconds % 60:02d} s"
