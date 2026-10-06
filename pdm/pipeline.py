"""Builds the database: loads the assets, runs the analysis and stores everything.

Two asset types are loaded, which shows the same pipeline serving different equipment:
  * the brushed DC motor (one run to failure): health index + experimental single-run RUL
  * a fleet of turbofan engines (NASA C-MAPSS FD001 test engines): health index + learned RUL
    with prediction interval, from a model trained only on the FD001 *train* engines
"""
import numpy as np
import pandas as pd

from . import db, health, rul, train
from .datasets import cmapss, motor
from .datasets.base import Run, store

FLEET_SUBSET = "FD001"
FLEET_SIZE = 20                       # engines loaded for the fleet view (evenly spread over the test set)
FLEET_MODEL_ID = f"turbofan_{FLEET_SUBSET}"


def _analyze(run: Run, rul_df: pd.DataFrame = None, method: str = None, db_path=None) -> dict:
    """Health index, status, alerts for a stored run; writes them to the database."""
    t = db.get_asset(run.asset_id, db_path)
    series = db.get_series(run.asset_id, db_path)
    failure = db.get_failure(run.asset_id, db_path)
    h = health.compute_health(series, t["type_id"], failure, rul_df)
    h.insert(0, "asset_id", run.asset_id)
    h["method"] = method
    alerts = health.build_alerts(run.asset_id, h, t["type_id"])
    db.save_health(h, db_path)
    db.replace_alerts(alerts, [run.asset_id], db_path)
    return {"asset_id": run.asset_id, "alerts": len(alerts)}


def load_motor(db_path=None) -> dict:
    run = motor.load()
    store(run, db_path)
    series = db.get_series(run.asset_id, db_path)
    pred, metrics = rul.single_run_estimate(series, run.failure_age)
    rul_df = pd.DataFrame({"rul_pred": pred, "rul_low": np.nan, "rul_high": np.nan})
    db.register_model("motor_single_run", motor.TYPE_ID, "single_run_experimental", source=motor.SOURCE,
                      params={"features": "smoothed sensors + overstress time"}, metrics=metrics, db_path=db_path)
    db.save_metrics(run.asset_id, metrics, db_path)
    result = _analyze(run, rul_df, "single_run_experimental", db_path)
    result["readings"] = len(series)
    return result


def load_fleet(db_path=None, subset: str = FLEET_SUBSET, size: int = FLEET_SIZE, retrain: bool = False) -> dict:
    """Loads a spread of held-out C-MAPSS test engines and scores them with the learned model."""
    if not cmapss.available(subset):
        return {"skipped": f"C-MAPSS {subset} not available (python scripts/fetch_cmapss.py)"}
    path = train.model_path(subset)
    if retrain or not path.exists():
        train.train_subset(subset, save=True)
    model = rul.RulModel.load(path)

    all_units = sorted(cmapss.read_raw(subset, "test")["unit"].unique())
    units = [int(u) for u in all_units[:: max(1, len(all_units) // size)][:size]]
    runs = cmapss.load(subset, "test", units=set(units))

    results_file = train.METRICS_FILE
    metrics_json = {}
    if results_file.exists():
        import json
        metrics_json = json.loads(results_file.read_text()).get(subset, {})
    db.register_model(
        f"turbofan_{subset}", "turbofan_engine", "learned", source=f"{cmapss.SOURCE} {subset} train engines",
        artifact_path=str(path.relative_to(train.MODELS_DIR.parent)),
        params={"rul_cap": model.rul_cap, "window": model.window, "n_regimes": model.n_regimes,
                "coverage": model.coverage}, metrics=metrics_json, db_path=db_path)
    if metrics_json:
        flat = {f"test_{k}": v for k, v in metrics_json["test"].items()}
        flat.update({f"baseline_{name}_{k}": v for name, m in metrics_json["baselines"].items() for k, v in m.items()})
        db.save_metrics(f"turbofan_{subset}", flat, db_path)

    alerts = 0
    for run in runs:
        store(run, db_path)
        series = db.get_series(run.asset_id, db_path)
        pred = model.predict(series)
        alerts += _analyze(run, pred, "learned", db_path)["alerts"]
    return {"engines": len(runs), "alerts": alerts, "model": str(path.name)}


def build(db_path=None, fleet: bool = True, retrain: bool = False) -> dict:
    """Rebuilds the whole database from the datasets."""
    db.init_db(db_path, reset=True)
    result = {"motor": load_motor(db_path)}
    if fleet:
        result["fleet"] = load_fleet(db_path, retrain=retrain)
    db.mark_current(db_path)        # last step: a half-built database never counts as current
    return result
