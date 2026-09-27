DB_NAME = "maintenance.db"

import sqlite3
import pandas as pd
from datetime import datetime
from pathlib import Path

# Base directory of this file
BASE_DIR = Path(__file__).resolve().parent
DB_NAME = BASE_DIR / "maintenance.db"
SCHEMA_FILE = BASE_DIR / "schema.sql"

def init_db(schema_file: Path = SCHEMA_FILE) -> None:
    """Creates the SQLite database and executes the schema script."""
    with sqlite3.connect(DB_NAME) as conn:
        with open(schema_file, "r") as f:
            conn.executescript(f.read())
        conn.commit()
    print("Database initialized successfully.")

def insert_machine(machine_id: str, name: str, m_type: str, location: str) -> None:
    """Adds a new machine to the registry."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO machines (machine_id, name, type, location)
            VALUES (?, ?, ?, ?)
            """,
            (machine_id, name, m_type, location),
        )
        conn.commit()

def insert_reading(machine_id: str, vibration: float, temperature: float, current: float, timestamp: str = None) -> None:
    """Inserts a single sensor reading record."""
    ts = timestamp if timestamp else datetime.utcnow().isoformat()
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO sensor_readings (timestamp, machine_id, vibration, temperature, current)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ts, machine_id, vibration, temperature, current),
        )
        conn.commit()

def insert_alert(machine_id: str, status_level: str, detected_issue: str, suggested_action: str, timestamp: str = None) -> None:
    """Records a detected condition warning and suggested action."""
    ts = timestamp if timestamp else datetime.utcnow().isoformat()
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO maintenance_alerts (timestamp, machine_id, status_level, detected_issue, suggested_action)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ts, machine_id, status_level, detected_issue, suggested_action),
        )
        conn.commit()

def get_recent_readings(machine_id: str, limit: int = 100) -> pd.DataFrame:
    """Queries sensor history and returns it as a Pandas DataFrame for the dashboard."""
    with sqlite3.connect(DB_NAME) as conn:
        query = """
            SELECT timestamp, vibration, temperature, current
            FROM sensor_readings
            WHERE machine_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """
        df = pd.read_sql_query(query, conn, params=(machine_id, limit))
        return df.iloc[::-1].reset_index(drop=True)

def get_latest_alert(machine_id: str) -> dict:
    """Retrieves the most recent alert for a specific machine."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT timestamp, status_level, detected_issue, suggested_action
            FROM maintenance_alerts
            WHERE machine_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (machine_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None