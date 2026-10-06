"""Data layer for the dashboard: reads assets, readings, health scores and alerts from SQLite.

Everything is driven by the asset type registry, so a new type of equipment shows up in the fleet
and asset views without dashboard changes.
"""
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# The package lives in the repository root, one level above this folder.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pdm import db, pipeline, registry  # noqa: E402

STATUS_RANK = {"Learning": -1, "Healthy": 0, "Warning": 1, "Critical": 2, "Failed": 3}
METHOD_LABELS = {
    "learned": "Learned model",
    "single_run_experimental": "Experimental (single run)",
}
NO_RUL_LABEL = "Health index only"

# Age and RUL are stored in the asset type's unit; show them in a friendlier one.
_DISPLAY_UNITS = {"s": (1 / 60, "min"), "cycle": (1.0, "cycles")}


def ensure_db() -> None:
    """Builds the database from the committed datasets unless a current one exists.

    A file left by an older version of the app (different schema) or by an interrupted build is
    replaced. A lock keeps two simultaneous sessions from building at the same time.
    """
    if db.is_current():
        return
    lock_path = db.DB_NAME.with_name(db.DB_NAME.name + ".lock")
    with open(lock_path, "w") as lock:
        try:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)     # another session may be building: wait, then re-check
        except ImportError:                      # no flock on this platform: build without the lock
            pass
        if not db.is_current():
            pipeline.build()


# ---------------------------------------------------------------- units
def unit_factor(type_id: str):
    """(factor, label): stored age units -> display units."""
    return _DISPLAY_UNITS.get(registry.get_type(type_id).age_unit, (1.0, registry.get_type(type_id).age_unit))


def format_amount(value, type_id: str, digits: int = 0) -> str:
    """A remaining life / age in display units, e.g. '47 cycles' or '12.4 min'."""
    if value is None or pd.isna(value):
        return "n/a"
    factor, label = unit_factor(type_id)
    return f"{value * factor:.{digits}f} {label}"


def format_rul(value, type_id: str, digits: int = 0) -> str:
    """An estimated RUL; a value at the training cap is shown as 'at least the cap'."""
    t = registry.get_type(type_id)
    if value is not None and not pd.isna(value) and t.rul_cap and value >= t.rul_cap - 1e-6:
        return f"≥ {format_amount(t.rul_cap, type_id, digits)}"
    return format_amount(value, type_id, digits)


def method_label(method, rul_pred) -> str:
    if method is None or pd.isna(method) or pd.isna(rul_pred):
        return NO_RUL_LABEL
    return METHOD_LABELS.get(method, str(method))


# ---------------------------------------------------------------- fleet
@dataclass
class Fleet:
    assets: pd.DataFrame
    health: pd.DataFrame
    failures: pd.DataFrame
    alerts: pd.DataFrame
    models: pd.DataFrame
    counts: pd.DataFrame        # readings per asset (assets still learning have readings but no health yet)


def load_fleet() -> Fleet:
    ensure_db()
    assets = db.list_assets()
    assets["metadata"] = assets["metadata"].map(lambda m: json.loads(m or "{}"))
    return Fleet(assets, db.get_health(), db.get_failures(), db.get_alerts(), db.get_models(),
                 db.get_reading_counts())


def data_stamp() -> tuple:
    """Changes whenever new readings, scores, alerts or failures reach the database (cache key for live data)."""
    ensure_db()
    return db.data_stamp()


def snapshot(fleet: Fleet, fraction: float = 1.0) -> pd.DataFrame:
    """The state of every asset at `fraction` of its recorded life (1.0 = latest reading).

    One row per asset, ordered by maintenance priority: worst status first, then the shortest
    estimated remaining life within an asset type.
    """
    fraction = min(max(float(fraction), 0.0), 1.0)
    fail_age = fleet.failures.set_index("asset_id")["age"].to_dict()
    names = fleet.assets.set_index("asset_id")
    counts = fleet.counts.set_index("asset_id") if len(fleet.counts) else pd.DataFrame(columns=["n_readings", "last_ts", "last_age"])
    rows = []

    def common(asset_id):
        type_id = names.loc[asset_id, "type_id"]
        return {"asset_id": asset_id, "name": names.loc[asset_id, "name"], "type_id": type_id,
                "type_name": registry.get_type(type_id).name,
                "live": bool(names.loc[asset_id, "metadata"].get("live", False))}

    for asset_id, h in fleet.health.groupby("asset_id", sort=True):
        h = h.sort_values("age").reset_index(drop=True)
        i = int(round(fraction * (len(h) - 1)))
        r = h.iloc[i]
        alerts = fleet.alerts[(fleet.alerts["asset_id"] == asset_id) & (fleet.alerts["ts"] <= r["ts"])]
        latest = alerts.iloc[0] if len(alerts) else None      # get_alerts returns newest first
        rows.append({
            **common(asset_id),
            "status": r["status"], "health_score": r["health_score"], "drift": r["drift"],
            "top_driver": r["top_driver"],
            "rul_pred": r["rul_pred"], "rul_low": r["rul_low"], "rul_high": r["rul_high"],
            "rul_true": max(fail_age[asset_id] - r["age"], 0.0) if asset_id in fail_age else np.nan,
            "age": r["age"], "ts": r["ts"], "position": i + 1, "n_readings": len(h),
            "method": method_label(r["method"], r["rul_pred"]),
            "open_alerts": len(alerts),
            "latest_level": latest["status_level"] if latest is not None else "",
            "latest_alert": latest["detected_issue"] if latest is not None else "",
            "latest_action": latest["suggested_action"] if latest is not None else "",
        })

    # assets with readings but no health scores yet are still learning their healthy baseline
    scored = set(fleet.health["asset_id"])
    for asset_id in fleet.assets["asset_id"]:
        if asset_id in scored:
            continue
        n = int(counts.loc[asset_id, "n_readings"]) if asset_id in counts.index else 0
        rows.append({
            **common(asset_id), "status": "Learning", "health_score": np.nan, "drift": np.nan, "top_driver": None,
            "rul_pred": np.nan, "rul_low": np.nan, "rul_high": np.nan, "rul_true": np.nan,
            "age": counts.loc[asset_id, "last_age"] if n else np.nan,
            "ts": counts.loc[asset_id, "last_ts"] if n else pd.NaT, "position": max(n, 1), "n_readings": n,
            "method": f"Learning baseline ({n}/{registry.get_type(names.loc[asset_id, 'type_id']).baseline_readings})",
            "open_alerts": 0, "latest_level": "", "latest_alert": "", "latest_action": "",
        })
    snap = pd.DataFrame(rows)
    snap["_rank"] = snap["status"].map(STATUS_RANK)
    snap = snap.sort_values(["_rank", "type_id", "rul_pred", "asset_id"], ascending=[False, True, True, True],
                            na_position="last").drop(columns="_rank").reset_index(drop=True)
    return snap


def status_counts(snap: pd.DataFrame) -> dict:
    counts = snap["status"].value_counts()
    return {s: int(counts.get(s, 0)) for s in STATUS_RANK}


def models_table(fleet: Fleet) -> pd.DataFrame:
    """The model registry in a flat, displayable form (text, so missing values read 'n/a')."""
    def num(value, fmt):
        return "n/a" if value is None or pd.isna(value) else format(value, fmt)

    rows = []
    for _, m in fleet.models.iterrows():
        metrics = json.loads(m["metrics"] or "{}")
        test = metrics.get("test", {})
        rows.append({
            "Model": m["model_id"], "Asset type": registry.get_type(m["type_id"]).name,
            "Kind": METHOD_LABELS.get(m["kind"], m["kind"]), "Trained on": m["source"],
            "Trained": pd.Timestamp(m["trained_at"]).strftime("%Y-%m-%d %H:%M"),
            "Test RMSE": num(test.get("rmse"), ".1f"),
            "Interval coverage": num(test.get("coverage"), ".2f"),
            "Evaluated on": f"{metrics['n_test_engines']} held-out engines" if "n_test_engines" in metrics
                            else "the single recorded run",
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- one asset
@dataclass
class AssetData:
    asset: dict
    type: registry.AssetType
    data: pd.DataFrame          # readings joined with health scores, in display units (see add_display_columns)
    failure: dict
    alerts: pd.DataFrame
    model: dict                 # {model_id, kind, source, metrics} or None
    method: str                 # label shown in the dashboard


def load_asset(asset_id: str) -> AssetData:
    ensure_db()
    asset = db.get_asset(asset_id)
    t = registry.get_type(asset["type_id"])
    series = db.get_series(asset_id)
    health = db.get_health(asset_id)[["age", "drift", "health_score", "status", "top_driver", "method",
                                       "rul_pred", "rul_low", "rul_high"]]
    data = series.merge(health, on="age", how="left") if len(series) else series.reindex(
        columns=[*series.columns, *health.columns.difference(series.columns)])
    # Live ingestion stores a reading first and scores it a moment later: show only scored readings (the rest
    # appear on the next refresh) instead of a newest row without status or health
    scored = data["health_score"].notna()
    if scored.any():
        data = data.loc[:scored[scored].index.max()].copy()
    failure = db.get_failure(asset_id)
    data["rul_true"] = (failure["age"] - data["age"]).clip(lower=0) if failure else np.nan
    factor, label = unit_factor(t.type_id)
    data["age_disp"] = data["age"] * factor
    for col in ("rul_pred", "rul_low", "rul_high", "rul_true"):
        data[f"{col}_disp"] = data[col] * factor

    method = data["method"].dropna().iloc[-1] if data["method"].notna().any() else None
    models = db.get_models(t.type_id)
    model = None
    if method is not None and not models.empty:
        cand = models[models["kind"] == method]
        cand = cand[cand["source"].fillna("").str.startswith(asset["source"] or "")] if len(cand) > 1 else cand
        if len(cand):
            m = cand.iloc[0]
            metrics = json.loads(m["metrics"] or "{}")
            model = {"model_id": m["model_id"], "kind": m["kind"], "source": m["source"], "metrics": metrics}
    if model is not None and model["kind"] == "single_run_experimental":
        model["metrics"] = db.get_metrics(asset_id)
    return AssetData(asset, t, data, failure, db.get_alerts(asset_id), model,
                     method_label(method, data["rul_pred"].dropna().iloc[-1] if data["rul_pred"].notna().any() else np.nan))


def asset_label(row) -> str:
    return f"{row['name']}  ({row['asset_id']})"
