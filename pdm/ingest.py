"""Live ingestion: validate readings as they arrive, store them, and score the asset.

This is the one code path for incoming data. The HTTP API (`pdm.api`), the simulator and the dashboard's
demo feed all call it, so a reading is treated the same however it arrives.

Rules for a reading
-------------------
* It names channels of the asset's type (`registry`); an unknown channel rejects the reading.
* Values are finite numbers. Channels may be missing; a missing operating-condition channel that the
  type groups its baseline by (e.g. the motor's supply regime) carries forward the last known value.
* `ts` is required. Re-sending a reading with an already stored timestamp is a harmless duplicate, so
  clients can retry safely. A reading older than the newest stored one is rejected (out of order).
* `age` (time since the asset started, in the type's age unit) is optional for types measured in
  seconds, where it is derived from `ts`, and required for the others (e.g. engine cycles).

After storing, the asset is re-scored from its full history with the same code as the offline pipeline:
health index and status, the learned RUL model when one is registered for the type, and alerts.
"""
import math
import sqlite3
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pandas as pd

from . import db, health, registry
from .rul import RulModel

MAX_BATCH = 1000
RESERVED_METADATA = {"recorded", "split"}     # set by the dataset loaders only; a device must not be able to claim them
ROOT = Path(__file__).resolve().parents[1]


class IngestError(ValueError):
    """The whole request is invalid (unknown asset, batch too large, ...)."""


class NotFound(IngestError):
    """The asset does not exist."""


class Conflict(IngestError):
    """The request clashes with what is stored (e.g. an asset id registered with another type)."""


@dataclass
class ReadingResult:
    index: int
    status: str                  # accepted | duplicate | rejected
    reason: str = ""


@dataclass
class IngestResult:
    asset_id: str
    accepted: int = 0
    duplicates: int = 0
    rejected: int = 0
    results: list = field(default_factory=list)
    state: dict = None           # the asset's current state after scoring (see `asset_state`)
    scoring_error: str = ""

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id, "accepted": self.accepted, "duplicates": self.duplicates,
            "rejected": [{"index": r.index, "reason": r.reason} for r in self.results if r.status == "rejected"],
            "state": self.state, "scoring_error": self.scoring_error or None,
        }


# one writer per asset at a time within a process (SQLite serialises writers across processes)
_locks: dict = {}
_locks_guard = threading.Lock()


def _lock(asset_id: str) -> threading.RLock:
    with _locks_guard:
        return _locks.setdefault(asset_id, threading.RLock())


# ---------------------------------------------------------------- assets
def register_asset(asset_id: str, type_id: str, name: str = None, site: str = None, source: str = None,
                   metadata: dict = None, db_path=None) -> dict:
    """Creates an asset. Registering the same id with the same type again changes nothing."""
    if not asset_id or not str(asset_id).strip():
        raise IngestError("asset_id must not be empty")
    try:
        registry.get_type(type_id)
    except KeyError as e:
        raise IngestError(str(e.args[0])) from None
    if db.asset_exists(asset_id, db_path):
        existing = db.get_asset(asset_id, db_path)
        if existing["type_id"] != type_id:
            raise Conflict(f"asset {asset_id!r} already exists with type {existing['type_id']!r}")
        return existing
    metadata = {k: v for k, v in (metadata or {}).items() if k not in RESERVED_METADATA}
    db.upsert_asset(asset_id, type_id, name or asset_id, site, source, metadata, db_path)
    return db.get_asset(asset_id, db_path)


def _asset_and_type(asset_id: str, db_path):
    if not db.asset_exists(asset_id, db_path):
        raise NotFound(f"unknown asset {asset_id!r}; register it first")
    asset = db.get_asset(asset_id, db_path)
    return asset, registry.get_type(asset["type_id"])


# ---------------------------------------------------------------- validation
def _timestamp(value) -> pd.Timestamp:
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError):
        raise ValueError(f"ts {value!r} is not a valid timestamp") from None
    if pd.isna(ts):
        raise ValueError("ts is required")
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts


def _number(value, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{what} must be a number, got {value!r}")
    if not math.isfinite(value):
        raise ValueError(f"{what} must be finite, got {value!r}")
    return float(value)


def _validate(raw: dict, t: registry.AssetType) -> tuple:
    """(ts, age or None, {channel: value}) of one raw reading, or ValueError with the reason."""
    if not isinstance(raw, dict):
        raise ValueError("a reading must be an object with ts, values (and age)")
    ts = _timestamp(raw.get("ts"))
    values = raw.get("values")
    if not isinstance(values, dict) or not values:
        raise ValueError("values must be a non-empty object of channel: number")
    known = {c.name for c in t.channels}
    unknown = sorted(set(values) - known)
    if unknown:
        raise ValueError(f"unknown channel(s) for {t.type_id}: {', '.join(map(str, unknown))}")
    clean = {ch: _number(v, f"value of {ch}") for ch, v in values.items()}
    age = raw.get("age")
    if age is not None:
        age = _number(age, "age")
        if age < 0:
            raise ValueError("age must not be negative")
    elif t.age_unit != "s":
        raise ValueError(f"age is required for assets measured in {t.age_unit}s")
    return ts, age, clean


# ---------------------------------------------------------------- ingestion
def ingest_readings(asset_id: str, readings: list, db_path=None, score: bool = True) -> IngestResult:
    """Validates and stores a batch of readings of one asset, then re-scores the asset.

    Valid readings are kept even if others in the batch are rejected; the result lists what happened to
    each one. Raises IngestError / NotFound only when the request as a whole cannot be processed.

    Several processes may ingest the same asset (e.g. two subscribers on one broker). The database allows
    one reading per asset and time, so if another writer stored one of ours between our check and our
    insert, the insert fails as a whole and we check again, which then sees it as a duplicate.
    """
    for attempt in (1, 2, 3):
        try:
            return _ingest_once(asset_id, readings, db_path, score)
        except sqlite3.IntegrityError:
            if attempt == 3:
                raise


def _ingest_once(asset_id: str, readings: list, db_path, score: bool) -> IngestResult:
    if not isinstance(readings, list) or not readings:
        raise IngestError("readings must be a non-empty list")
    if len(readings) > MAX_BATCH:
        raise IngestError(f"at most {MAX_BATCH} readings per request, got {len(readings)}")
    asset, t = _asset_and_type(asset_id, db_path)
    result = IngestResult(asset_id)

    with _lock(asset_id):
        parsed = []                                   # (position, ts, age, values) of the valid ones
        for i, raw in enumerate(readings):
            try:
                parsed.append((i, *_validate(raw, t)))
            except ValueError as e:
                result.results.append(ReadingResult(i, "rejected", str(e)))
        parsed.sort(key=lambda p: (p[1], p[0]))        # by time; stable for equal timestamps

        last = db.get_last_reading(asset_id, db_path)
        seen = db.existing_timestamps(asset_id, parsed[0][1], db_path) if parsed else set()
        first_ts = db.get_first_ts(asset_id, db_path)
        regime = db.get_last_value(asset_id, t.regime_channel, db_path) if t.regime_channel else None
        last_ts, last_age = (last["ts"], last["age"]) if last else (None, -math.inf)

        rows = []
        for i, ts, age, values in parsed:
            stored_key = ts.strftime("%Y-%m-%d %H:%M:%S.%f")
            if stored_key in seen:
                result.results.append(ReadingResult(i, "duplicate"))
                continue
            if last_ts is not None and ts <= last_ts:
                result.results.append(ReadingResult(i, "rejected", "out of order: older than the newest stored reading"))
                continue
            if first_ts is None:
                first_ts = ts
            age = age if age is not None else (ts - first_ts).total_seconds()
            if age <= last_age:
                result.results.append(ReadingResult(i, "rejected", f"age must increase (newest stored age is {last_age:g})"))
                continue
            if t.regime_channel:
                if t.regime_channel in values:
                    regime = values[t.regime_channel]
                elif regime is not None:
                    values = {**values, t.regime_channel: regime}      # carry the last known condition forward
                else:
                    result.results.append(ReadingResult(i, "rejected", f"{t.regime_channel} is required for the first reading"))
                    continue
            rows.append({"ts": ts, "age": age, **values})
            seen.add(stored_key)
            last_ts, last_age = ts, age
            result.results.append(ReadingResult(i, "accepted"))

        if rows:
            db.append_readings(asset_id, pd.DataFrame(rows), db_path)
        result.accepted = len(rows)
        result.duplicates = sum(r.status == "duplicate" for r in result.results)
        result.rejected = sum(r.status == "rejected" for r in result.results)
        result.results.sort(key=lambda r: r.index)

        if score and rows:
            try:
                result.state = score_asset(asset_id, db_path)
            except Exception as e:                     # the data is stored; scoring can be retried
                result.scoring_error = f"{type(e).__name__}: {e}"
        if result.state is None:
            result.state = asset_state(asset_id, db_path)
    return result


def report_failure(asset_id: str, ts, age: float = None, mode: str = None, db_path=None) -> dict:
    """Records that an asset failed (a maintenance outcome) and re-scores it. Returns the asset's state."""
    asset, t = _asset_and_type(asset_id, db_path)
    with _lock(asset_id):
        ts = _timestamp(ts)
        if age is None:
            if t.age_unit != "s":
                raise IngestError(f"age is required for assets measured in {t.age_unit}s")
            first = db.get_first_ts(asset_id, db_path)
            age = (ts - first).total_seconds() if first is not None else 0.0
        else:
            age = _number(age, "age")
        db.set_failure(asset_id, ts, age, mode, observed=True, db_path=db_path)
        score_asset(asset_id, db_path)
    return asset_state(asset_id, db_path)


# ---------------------------------------------------------------- scoring
@lru_cache(maxsize=8)
def _load_model(path: str, mtime_ns: int) -> RulModel:
    return RulModel.load(path)


def learned_model_for(asset: dict, t: registry.AssetType, db_path=None):
    """The registered learned RUL model that fits this asset (same type, preferably same source), or None."""
    models = db.get_models(t.type_id, db_path)
    models = models[models["kind"] == "learned"]
    if models.empty:
        return None
    preferred = models[models["source"].fillna("").str.startswith(asset.get("source") or "\0")]
    row = (preferred if len(preferred) else models).iloc[0]
    path = ROOT / row["artifact_path"] if row["artifact_path"] else None
    if path is None or not path.exists():
        return None
    return _load_model(str(path), path.stat().st_mtime_ns)


def score_asset(asset_id: str, db_path=None) -> dict:
    """Health, status, RUL and alerts of an asset from its whole stored history. Returns its state.

    Until the asset has `baseline_readings` readings there is no healthy baseline to compare with, so
    it is reported as still learning instead of being scored against a handful of points.
    """
    asset, t = _asset_and_type(asset_id, db_path)
    with _lock(asset_id):
        series = db.get_series(asset_id, db_path)
        if len(series) < t.baseline_readings:
            return asset_state(asset_id, db_path)
        failure = db.get_failure(asset_id, db_path)
        model = learned_model_for(asset, t, db_path)
        rul = model.predict(series) if model is not None else None
        scored = health.compute_health(series, t.type_id, failure, rul)
        scored.insert(0, "asset_id", asset_id)
        scored["method"] = "learned" if model is not None else None
        db.save_health(scored, db_path)
        db.sync_alerts(health.build_alerts(asset_id, scored, t.type_id), db_path)
    return asset_state(asset_id, db_path)


def asset_state(asset_id: str, db_path=None) -> dict:
    """Where an asset stands now: status, health, RUL estimate, or 'Learning' while the baseline forms."""
    asset, t = _asset_and_type(asset_id, db_path)
    counts = db.get_reading_counts(db_path)
    n = int(counts.loc[counts["asset_id"] == asset_id, "n_readings"].sum())
    scores = db.get_health(asset_id, db_path)
    if scores.empty:
        return {"asset_id": asset_id, "status": "Learning", "readings": n,
                "readings_needed": t.baseline_readings, "age_unit": t.age_unit}
    last = scores.iloc[-1]

    def num(v):
        return None if pd.isna(v) else float(v)

    return {
        "asset_id": asset_id, "status": last["status"], "readings": n, "age": float(last["age"]),
        "age_unit": t.age_unit, "ts": last["ts"].isoformat(), "health_score": num(last["health_score"]),
        "top_driver": None if pd.isna(last["top_driver"]) else last["top_driver"],
        "rul": num(last["rul_pred"]), "rul_low": num(last["rul_low"]), "rul_high": num(last["rul_high"]),
        "method": None if pd.isna(last["method"]) else last["method"],
    }
