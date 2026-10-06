import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# Base directory of this file
BASE_DIR = Path(__file__).resolve().parent
DB_NAME = Path(os.environ.get("MAINTENANCE_DB", BASE_DIR / "maintenance.db"))
SCHEMA_FILE = BASE_DIR / "schema.sql"

READING_COLUMNS = [
    "timestamp", "machine_id", "source_file", "phase", "regime", "speed_rpm",
    "current", "voltage", "temp_motor", "temp_ambient", "vib_1x", "vib_5x",
    "vib_7x", "vib_band_0_4k", "vib_band_4_8k", "vib_band_8_16k",
    "vib_band_16_26k", "is_failed", "rul_true_s",
]
HEALTH_COLUMNS = [
    "timestamp", "machine_id", "drift", "health_score", "status",
    "top_driver", "rul_pred_s",
]
ALERT_COLUMNS = [
    "timestamp", "machine_id", "status_level", "detected_issue", "suggested_action",
]


@contextmanager
def _connect(db_path=None):
    """Opens a connection, commits on success and always closes it."""
    conn = sqlite3.connect(db_path or DB_NAME)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")


def _to_iso(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series).dt.strftime("%Y-%m-%d %H:%M:%S.%f")


def init_db(db_path=None, schema_file: Path = SCHEMA_FILE, reset: bool = False) -> None:
    """Creates the SQLite database and executes the schema script.

    With reset=True the existing database file is deleted first.
    """
    path = Path(db_path or DB_NAME)
    if reset and path.exists():
        path.unlink()
    with _connect(path) as conn:
        conn.executescript(Path(schema_file).read_text())


def insert_machine(machine_id: str, name: str, m_type: str, location: str, db_path=None) -> None:
    """Adds a new machine to the registry."""
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO machines (machine_id, name, type, location) VALUES (?, ?, ?, ?)",
            (machine_id, name, m_type, location),
        )


def insert_reading(machine_id: str, timestamp: str = None, db_path=None, **values) -> None:
    """Inserts a single sensor reading, e.g. insert_reading("M1", vib_1x=0.1, temp_motor=40)."""
    unknown = set(values) - set(READING_COLUMNS)
    if unknown:
        raise ValueError(f"Unknown sensor columns: {sorted(unknown)}")
    row = {"timestamp": timestamp or _now(), "machine_id": machine_id, **values}
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    with _connect(db_path) as conn:
        conn.execute(f"INSERT INTO sensor_readings ({cols}) VALUES ({marks})", list(row.values()))


def insert_readings_bulk(df: pd.DataFrame, db_path=None) -> int:
    """Inserts many readings at once from a DataFrame using READING_COLUMNS."""
    out = df.reindex(columns=READING_COLUMNS).copy()
    out["timestamp"] = _to_iso(out["timestamp"])
    out = out.astype(object).where(out.notna(), None)
    with _connect(db_path) as conn:
        conn.executemany(
            f"INSERT INTO sensor_readings ({', '.join(READING_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in READING_COLUMNS)})",
            out.values.tolist(),
        )
    return len(out)


def insert_health_bulk(df: pd.DataFrame, db_path=None) -> int:
    """Replaces the stored health scores for the machines present in df."""
    out = df.reindex(columns=HEALTH_COLUMNS).copy()
    out["timestamp"] = _to_iso(out["timestamp"])
    out = out.astype(object).where(out.notna(), None)
    with _connect(db_path) as conn:
        conn.executemany("DELETE FROM health_scores WHERE machine_id = ?",
                         [(m,) for m in out["machine_id"].unique()])
        conn.executemany(
            f"INSERT INTO health_scores ({', '.join(HEALTH_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in HEALTH_COLUMNS)})",
            out.values.tolist(),
        )
    return len(out)


def insert_alert(machine_id: str, status_level: str, detected_issue: str,
                 suggested_action: str, timestamp: str = None, db_path=None) -> None:
    """Records a detected condition warning and suggested action."""
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO maintenance_alerts (timestamp, machine_id, status_level, detected_issue, suggested_action)
            VALUES (?, ?, ?, ?, ?)
            """,
            (timestamp or _now(), machine_id, status_level, detected_issue, suggested_action),
        )


def replace_alerts(df: pd.DataFrame, db_path=None) -> int:
    """Replaces stored alerts for the machines present in df (used when the analysis is re-run)."""
    out = df.reindex(columns=ALERT_COLUMNS).copy()
    out["timestamp"] = _to_iso(out["timestamp"])
    with _connect(db_path) as conn:
        conn.executemany("DELETE FROM maintenance_alerts WHERE machine_id = ?",
                         [(m,) for m in out["machine_id"].unique()])
        conn.executemany(
            f"INSERT INTO maintenance_alerts ({', '.join(ALERT_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in ALERT_COLUMNS)})",
            out.values.tolist(),
        )
    return len(out)


def save_metrics(metrics: dict, db_path=None) -> None:
    """Stores model evaluation numbers (name -> value)."""
    with _connect(db_path) as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO model_metrics (name, value) VALUES (?, ?)",
            [(k, float(v)) for k, v in metrics.items()],
        )


def get_metrics(db_path=None) -> dict:
    with _connect(db_path) as conn:
        return dict(conn.execute("SELECT name, value FROM model_metrics").fetchall())


def _read(query: str, params=(), db_path=None, parse_dates=("timestamp",)) -> pd.DataFrame:
    with _connect(db_path) as conn:
        return pd.read_sql_query(query, conn, params=params, parse_dates=list(parse_dates))


def get_machines(db_path=None) -> pd.DataFrame:
    return _read("SELECT * FROM machines ORDER BY machine_id", db_path=db_path, parse_dates=())


def get_readings(machine_id: str, db_path=None) -> pd.DataFrame:
    """All readings of a machine in time order."""
    return _read(
        "SELECT * FROM sensor_readings WHERE machine_id = ? ORDER BY timestamp",
        (machine_id,), db_path,
    )


def get_recent_readings(machine_id: str, limit: int = 100, db_path=None) -> pd.DataFrame:
    """The latest `limit` readings of a machine, oldest first."""
    df = _read(
        "SELECT * FROM sensor_readings WHERE machine_id = ? ORDER BY timestamp DESC LIMIT ?",
        (machine_id, limit), db_path,
    )
    return df.iloc[::-1].reset_index(drop=True)


def get_health(machine_id: str, db_path=None) -> pd.DataFrame:
    return _read(
        "SELECT * FROM health_scores WHERE machine_id = ? ORDER BY timestamp",
        (machine_id,), db_path,
    )


def get_alerts(machine_id: str, db_path=None) -> pd.DataFrame:
    """All alerts of a machine, newest first."""
    return _read(
        "SELECT * FROM maintenance_alerts WHERE machine_id = ? ORDER BY timestamp DESC, alert_id DESC",
        (machine_id,), db_path,
    )


def get_latest_alert(machine_id: str, db_path=None):
    """Retrieves the most recent alert for a specific machine, or None."""
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT timestamp, status_level, detected_issue, suggested_action
            FROM maintenance_alerts
            WHERE machine_id = ?
            ORDER BY timestamp DESC, alert_id DESC
            LIMIT 1
            """,
            (machine_id,),
        ).fetchone()
        return dict(row) if row else None
