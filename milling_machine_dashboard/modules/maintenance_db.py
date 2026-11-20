
import sqlite3
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "database" / "milling.db"


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def initialise_database():
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS milling_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment INTEGER NOT NULL,
                case_id TEXT,
                run_id TEXT,
                wear_value REAL NOT NULL,
                value_source TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT DEFAULT 'Open',
                created_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS milling_work_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id INTEGER,
                task TEXT NOT NULL,
                assigned_to TEXT,
                priority TEXT NOT NULL,
                status TEXT DEFAULT 'Open',
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (alert_id)
                    REFERENCES milling_alerts(id)
            )
        """)


def add_alert(experiment, case_id, run_id, wear_value,
              value_source, severity, message):

    with connect() as conn:
        conn.execute("""
            INSERT INTO milling_alerts
            (experiment, case_id, run_id, wear_value,
             value_source, severity, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            int(experiment),
            str(case_id),
            str(run_id),
            float(wear_value),
            value_source,
            severity,
            message,
            datetime.now().isoformat(timespec="seconds")
        ))


def get_alerts():
    with connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT * FROM milling_alerts
            ORDER BY id DESC
        """).fetchall()
        return [dict(row) for row in rows]


def update_alert_status(alert_id, status):
    with connect() as conn:
        conn.execute("""
            UPDATE milling_alerts
            SET status = ?
            WHERE id = ?
        """, (status, int(alert_id)))


def add_work_order(alert_id, task, assigned_to, priority, notes=""):
    now = datetime.now().isoformat(timespec="seconds")

    with connect() as conn:
        conn.execute("""
            INSERT INTO milling_work_orders
            (alert_id, task, assigned_to, priority,
             status, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'Open', ?, ?, ?)
        """, (
            alert_id,
            task,
            assigned_to,
            priority,
            notes,
            now,
            now
        ))


def get_work_orders():
    with connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT * FROM milling_work_orders
            ORDER BY id DESC
        """).fetchall()
        return [dict(row) for row in rows]


def update_work_order_status(order_id, status):
    now = datetime.now().isoformat(timespec="seconds")

    with connect() as conn:
        conn.execute("""
            UPDATE milling_work_orders
            SET status = ?, updated_at = ?
            WHERE id = ?
        """, (status, now, int(order_id)))
