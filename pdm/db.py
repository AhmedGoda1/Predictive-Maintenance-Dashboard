"""SQLite access for the asset-agnostic schema."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import registry

ROOT = Path(__file__).resolve().parents[1]
DB_NAME = Path(os.environ.get("MAINTENANCE_DB", ROOT / "maintenance.db"))
SCHEMA_FILE = Path(__file__).with_name("schema.sql")

# Bump when schema.sql changes incompatibly. A database file left behind by an older version (e.g. on a
# deployed app, where the file outlives code updates) is then rebuilt instead of queried.
SCHEMA_VERSION = 2

HEALTH_COLUMNS = ["asset_id", "ts", "age", "drift", "health_score", "status", "top_driver",
                  "method", "rul_pred", "rul_low", "rul_high"]
ALERT_COLUMNS = ["asset_id", "ts", "status_level", "detected_issue", "suggested_action"]


@contextmanager
def connect(db_path=None):
    """Opens a connection, commits on success and always closes it."""
    conn = sqlite3.connect(db_path or DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _iso(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series).dt.strftime("%Y-%m-%d %H:%M:%S.%f")


def _clean(df: pd.DataFrame) -> list:
    """DataFrame -> list of row lists with NaN as None (SQLite NULL)."""
    return df.astype(object).where(df.notna(), None).values.tolist()


def _read(query, params=(), db_path=None, dates=("ts",)) -> pd.DataFrame:
    with connect(db_path) as conn:
        df = pd.read_sql_query(query, conn, params=params)
    for col in dates:
        if col in df:
            df[col] = pd.to_datetime(df[col])
    return df


# ---------------------------------------------------------------- setup
def init_db(db_path=None, reset: bool = False) -> None:
    """Creates the database, applies the schema and registers all known asset types."""
    path = Path(db_path or DB_NAME)
    if reset and path.exists():
        path.unlink()
    with connect(path) as conn:
        conn.executescript(SCHEMA_FILE.read_text())
    for asset_type in registry.all_types():
        register_asset_type(asset_type, path)


def mark_current(db_path=None) -> None:
    """Stamps the database as complete and matching this version of the code (call after a build)."""
    with connect(db_path) as conn:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def is_current(db_path=None) -> bool:
    """True when the database file exists, was fully built by this schema version and has assets."""
    path = Path(db_path or DB_NAME)
    if not path.exists():
        return False
    try:
        with connect(path) as conn:
            if conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                return False
            return conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0] > 0
    except sqlite3.DatabaseError:
        return False


def register_asset_type(t: registry.AssetType, db_path=None) -> None:
    config = {
        "regime_channel": t.regime_channel, "limits": [list(x) for x in t.limits],
        "drift_scale": t.drift_scale, "healthy_min": t.healthy_min, "warning_min": t.warning_min,
        "rul_warning": t.rul_warning, "rul_critical": t.rul_critical, "rul_cap": t.rul_cap,
    }
    with connect(db_path) as conn:
        conn.execute("INSERT OR REPLACE INTO asset_types (type_id, name, age_unit, config) VALUES (?,?,?,?)",
                     (t.type_id, t.name, t.age_unit, json.dumps(config)))
        conn.execute("DELETE FROM channel_defs WHERE type_id = ?", (t.type_id,))
        conn.executemany(
            "INSERT INTO channel_defs (type_id, channel, unit, kind, description, health) VALUES (?,?,?,?,?,?)",
            [(t.type_id, c.name, c.unit, c.kind, c.description, c.health) for c in t.channels],
        )


# ---------------------------------------------------------------- assets
def upsert_asset(asset_id: str, type_id: str, name: str, site: str = None,
                 source: str = None, metadata: dict = None, db_path=None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO assets (asset_id, type_id, name, site, source, metadata) VALUES (?,?,?,?,?,?)",
            (asset_id, type_id, name, site, source, json.dumps(metadata or {})),
        )


def list_assets(type_id: str = None, db_path=None) -> pd.DataFrame:
    if type_id:
        return _read("SELECT * FROM assets WHERE type_id = ? ORDER BY asset_id", (type_id,), db_path, dates=())
    return _read("SELECT * FROM assets ORDER BY asset_id", db_path=db_path, dates=())


def get_asset(asset_id: str, db_path=None) -> dict:
    df = _read("SELECT * FROM assets WHERE asset_id = ?", (asset_id,), db_path, dates=())
    if df.empty:
        raise KeyError(f"Unknown asset {asset_id!r}")
    row = df.iloc[0].to_dict()
    row["metadata"] = json.loads(row["metadata"] or "{}")
    return row


# ---------------------------------------------------------------- readings
def insert_series(asset_id: str, series: pd.DataFrame, db_path=None) -> int:
    """Replaces an asset's readings with `series`.

    `series` is wide: columns ts, age and one column per channel (NaN = missing).
    Returns the number of readings stored.
    """
    channels = [c for c in series.columns if c not in ("ts", "age")]
    df = series.sort_values("age").reset_index(drop=True)
    with connect(db_path) as conn:
        conn.execute("DELETE FROM measurements WHERE reading_id IN "
                     "(SELECT reading_id FROM readings WHERE asset_id = ?)", (asset_id,))
        conn.execute("DELETE FROM readings WHERE asset_id = ?", (asset_id,))
        conn.executemany(
            "INSERT INTO readings (asset_id, ts, age) VALUES (?,?,?)",
            [(asset_id, t, a) for t, a in zip(_iso(df["ts"]), df["age"].astype(float))],
        )
        ids = [r[0] for r in conn.execute(
            "SELECT reading_id FROM readings WHERE asset_id = ? ORDER BY reading_id", (asset_id,))]
        long = df[channels].copy()
        long.insert(0, "reading_id", ids)
        long = long.melt(id_vars="reading_id", var_name="channel", value_name="value").dropna(subset=["value"])
        conn.executemany("INSERT INTO measurements (reading_id, channel, value) VALUES (?,?,?)",
                         _clean(long))
    return len(df)


def get_series(asset_id: str, db_path=None) -> pd.DataFrame:
    """The asset's readings as a wide frame: ts, age and one column per channel."""
    long = _read(
        """SELECT r.reading_id, r.ts, r.age, m.channel, m.value
           FROM readings r LEFT JOIN measurements m USING (reading_id)
           WHERE r.asset_id = ? ORDER BY r.age""",
        (asset_id,), db_path,
    )
    if long.empty:
        return pd.DataFrame(columns=["ts", "age"])
    base = long.drop_duplicates("reading_id")[["reading_id", "ts", "age"]].set_index("reading_id")
    wide = long.dropna(subset=["channel"]).pivot(index="reading_id", columns="channel", values="value")
    out = base.join(wide).sort_values("age").reset_index(drop=True)
    out.columns.name = None
    return out


# ---------------------------------------------------------------- failure, segments
def set_failure(asset_id: str, ts, age: float, mode: str = None, observed: bool = True, db_path=None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO failure_events (asset_id, ts, age, mode, observed) VALUES (?,?,?,?,?)",
            (asset_id, pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M:%S.%f"), float(age), mode, int(observed)),
        )


def get_failure(asset_id: str, db_path=None):
    df = _read("SELECT * FROM failure_events WHERE asset_id = ?", (asset_id,), db_path)
    return None if df.empty else df.iloc[0].to_dict()


def get_failures(db_path=None) -> pd.DataFrame:
    """The failure events of all assets."""
    return _read("SELECT * FROM failure_events ORDER BY asset_id", db_path=db_path)


def set_segments(asset_id: str, segments: pd.DataFrame, db_path=None) -> None:
    """segments: columns name, start_ts, end_ts."""
    with connect(db_path) as conn:
        conn.execute("DELETE FROM segments WHERE asset_id = ?", (asset_id,))
        conn.executemany(
            "INSERT INTO segments (asset_id, name, start_ts, end_ts) VALUES (?,?,?,?)",
            [(asset_id, n, s, e) for n, s, e in zip(segments["name"], _iso(segments["start_ts"]),
                                                     _iso(segments["end_ts"]))],
        )


def get_segments(asset_id: str, db_path=None) -> pd.DataFrame:
    return _read("SELECT name, start_ts, end_ts FROM segments WHERE asset_id = ? ORDER BY start_ts",
                 (asset_id,), db_path, dates=("start_ts", "end_ts"))


# ---------------------------------------------------------------- analysis output
def save_health(df: pd.DataFrame, db_path=None) -> int:
    """Replaces the stored health scores of the assets present in df."""
    out = df.reindex(columns=HEALTH_COLUMNS).copy()
    out["ts"] = _iso(out["ts"])
    with connect(db_path) as conn:
        conn.executemany("DELETE FROM health_scores WHERE asset_id = ?",
                         [(a,) for a in out["asset_id"].unique()])
        conn.executemany(
            f"INSERT INTO health_scores ({', '.join(HEALTH_COLUMNS)}) VALUES ({', '.join('?' * len(HEALTH_COLUMNS))})",
            _clean(out),
        )
    return len(out)


def get_health(asset_id: str = None, db_path=None) -> pd.DataFrame:
    """Health scores of one asset, or of every asset when asset_id is None."""
    if asset_id is None:
        return _read("SELECT * FROM health_scores ORDER BY asset_id, age", db_path=db_path)
    return _read("SELECT * FROM health_scores WHERE asset_id = ? ORDER BY age", (asset_id,), db_path)


def replace_alerts(df: pd.DataFrame, asset_ids, db_path=None) -> int:
    """Replaces the stored alerts of `asset_ids` with those in df (which may be empty)."""
    out = df.reindex(columns=ALERT_COLUMNS).copy()
    out["ts"] = _iso(out["ts"]) if len(out) else out["ts"]
    with connect(db_path) as conn:
        conn.executemany("DELETE FROM maintenance_alerts WHERE asset_id = ?", [(a,) for a in asset_ids])
        conn.executemany(
            f"INSERT INTO maintenance_alerts ({', '.join(ALERT_COLUMNS)}) VALUES ({', '.join('?' * len(ALERT_COLUMNS))})",
            _clean(out),
        )
    return len(out)


def insert_alert(asset_id: str, status_level: str, detected_issue: str, suggested_action: str,
                 ts: str = None, db_path=None) -> None:
    ts = ts or datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO maintenance_alerts (asset_id, ts, status_level, detected_issue, suggested_action) "
            "VALUES (?,?,?,?,?)", (asset_id, ts, status_level, detected_issue, suggested_action))


def get_alerts(asset_id: str = None, db_path=None) -> pd.DataFrame:
    """Alerts, newest first; all assets when asset_id is None."""
    where, params = ("WHERE asset_id = ?", (asset_id,)) if asset_id else ("", ())
    return _read(f"SELECT * FROM maintenance_alerts {where} ORDER BY ts DESC, alert_id DESC", params, db_path)


def get_latest_alert(asset_id: str, db_path=None):
    df = get_alerts(asset_id, db_path)
    return None if df.empty else df.iloc[0].to_dict()


# ---------------------------------------------------------------- models and metrics
def register_model(model_id: str, type_id: str, kind: str, source: str = None, artifact_path: str = None,
                   params: dict = None, metrics: dict = None, db_path=None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO models (model_id, type_id, kind, source, trained_at, artifact_path, params, metrics) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (model_id, type_id, kind, source, datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" "),
             artifact_path, json.dumps(params or {}), json.dumps(metrics or {})),
        )


def get_models(type_id: str = None, db_path=None) -> pd.DataFrame:
    if type_id:
        return _read("SELECT * FROM models WHERE type_id = ? ORDER BY model_id", (type_id,), db_path, dates=("trained_at",))
    return _read("SELECT * FROM models ORDER BY model_id", db_path=db_path, dates=("trained_at",))


def save_metrics(scope: str, metrics: dict, db_path=None) -> None:
    with connect(db_path) as conn:
        conn.executemany("INSERT OR REPLACE INTO metrics (scope, name, value) VALUES (?,?,?)",
                         [(scope, k, float(v)) for k, v in metrics.items()])


def get_metrics(scope: str, db_path=None) -> dict:
    with connect(db_path) as conn:
        return dict(conn.execute("SELECT name, value FROM metrics WHERE scope = ?", (scope,)).fetchall())
