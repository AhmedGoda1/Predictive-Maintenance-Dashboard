"""Data layer for the dashboard: reads readings, health scores and alerts from SQLite."""
import sys
from pathlib import Path

import pandas as pd

# The database modules live in the repository root, one level above this folder.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import build_db  # noqa: E402
import db_manager  # noqa: E402
import ingest  # noqa: E402

MACHINE_ID = ingest.MACHINE_ID


def ensure_db() -> None:
    """Builds the database from the committed dataset when it does not exist yet
    (e.g. on a fresh deployment, since maintenance.db is not committed)."""
    if not db_manager.DB_NAME.exists():
        build_db.build()


def load_machine_data(machine_id: str = MACHINE_ID):
    """Returns (machine row, readings joined with health scores, alerts, model metrics)."""
    ensure_db()
    machine = db_manager.get_machines().set_index("machine_id").loc[machine_id]
    readings = db_manager.get_readings(machine_id)
    health = db_manager.get_health(machine_id)[
        ["timestamp", "drift", "health_score", "status", "top_driver", "rul_pred_s"]
    ]
    data = readings.merge(health, on="timestamp", how="left").reset_index(drop=True)
    alerts = db_manager.get_alerts(machine_id)
    return machine, data, alerts, db_manager.get_metrics()


def format_duration(seconds) -> str:
    """Seconds -> '12 min 05 s'."""
    if pd.isna(seconds):
        return "n/a"
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60} min {seconds % 60:02d} s"
