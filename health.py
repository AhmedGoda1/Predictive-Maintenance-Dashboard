"""Health index, status, alerts and RUL estimate for the monitored motor.

How it works
------------
* Health index: vibration features (1x harmonic and the 0-4 kHz / 4-8 kHz
  bands) are compared with a healthy baseline taken from the first readings
  of the same supply regime (3 V or 5 V), because the regime changes the
  vibration level by itself. The deviation is turned into a 0-100 score.
* Status: Healthy / Warning / Critical from the score plus a motor
  temperature rule; "Failed" once the motor has stopped. A status only
  changes after it has held for a few consecutive readings.
* Alerts: written whenever the status gets worse, with the feature that
  drives the deviation and a suggested action.
* RUL: random forest on smoothed sensor features plus accumulated overstress
  time. Only one run-to-failure exists, so the estimate is evaluated with
  blocked cross-validation (and a forward-in-time split) and is indicative only.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

import db_manager

VIB_FEATURES = ["vib_1x", "vib_band_0_4k", "vib_band_4_8k"]
BASELINE_ROWS = 20          # healthy reference = first N readings of each regime
SMOOTH_WINDOW = 7           # rolling median over readings
DEBOUNCE = 3                # readings a new status must hold before it is adopted
HEALTHY_MIN, WARNING_MIN = 70, 40
TEMP_WARNING, TEMP_CRITICAL = 60.0, 70.0   # degC, motor surface
STATUS_RANK = {"Healthy": 0, "Warning": 1, "Critical": 2, "Failed": 3}

RUL_FEATURES = ["vib_1x", "vib_band_0_4k", "vib_band_4_8k", "temp_motor",
                "current", "speed_rpm", "is_5v", "overstress_s"]
CV_BLOCK = 30               # readings per cross-validation block
FORWARD_TRAIN_FRACTION = 0.75

ISSUES = {
    "vib_1x": (
        "Elevated 1x vibration (imbalance, misalignment or commutator wear)",
        "Inspect shaft balance, alignment and the commutator surface",
    ),
    "vib_band_0_4k": (
        "Broadband vibration rising (brush / commutator wear)",
        "Inspect brushes and commutator for wear and plan a replacement",
    ),
    "vib_band_4_8k": (
        "High-frequency vibration rising (bearing wear or brush arcing)",
        "Check bearings and brush contact, look for arcing marks",
    ),
    "temp_motor": (
        "Motor surface temperature above limit",
        "Reduce supply voltage / load and check cooling and ventilation",
    ),
}
FAILED_ISSUE = (
    "Motor stopped: supply current and speed collapsed",
    "Take the motor out of service; inspect windings, brushes and commutator",
)


def _baselines(df: pd.DataFrame) -> dict:
    """Median of the first BASELINE_ROWS healthy readings for each regime."""
    ok = df[df["is_failed"] == 0]
    return {
        regime: g.head(BASELINE_ROWS)[VIB_FEATURES].median()
        for regime, g in ok.groupby("regime")
    }


def _debounce(raw: list, n: int = DEBOUNCE) -> list:
    """A status change is adopted only after it has been seen n times in a row."""
    out, current, streak, candidate = [], raw[0], 0, raw[0]
    for s in raw:
        if s == current:
            streak, candidate = 0, current
        elif s == candidate:
            streak += 1
            if streak >= n or s == "Failed":
                current, streak = s, 0
        else:
            candidate, streak = s, 1
            if n <= 1 or s == "Failed":
                current, streak = s, 0
        out.append(current)
    return out


def compute_health(readings: pd.DataFrame) -> pd.DataFrame:
    """Per-reading drift, health score, status and the feature driving the deviation."""
    df = readings.sort_values("timestamp").reset_index(drop=True)
    base = _baselines(df)
    smooth = df[VIB_FEATURES + ["temp_motor"]].rolling(SMOOTH_WINDOW, min_periods=1).median()

    ratios = pd.DataFrame(index=df.index, columns=VIB_FEATURES, dtype=float)
    for f in VIB_FEATURES:
        ref = df["regime"].map(lambda r: base[r][f])
        ratios[f] = np.log(smooth[f].clip(lower=1e-6) / ref.clip(lower=1e-6)).clip(lower=0)

    drift = ratios.mean(axis=1)
    score = 100 * np.exp(-drift)

    raw_status = np.where(score >= HEALTHY_MIN, "Healthy",
                          np.where(score >= WARNING_MIN, "Warning", "Critical")).astype(object)
    temp = smooth["temp_motor"]
    raw_status[(temp >= TEMP_WARNING).to_numpy() & (raw_status == "Healthy")] = "Warning"
    raw_status[(temp >= TEMP_CRITICAL).to_numpy()] = "Critical"
    raw_status[df["is_failed"].to_numpy() == 1] = "Failed"

    driver = ratios.idxmax(axis=1).where(drift > 0.05, None)
    hot = (temp >= TEMP_WARNING) & (drift < 0.5)
    driver = driver.where(~hot, "temp_motor")

    out = pd.DataFrame({
        "timestamp": df["timestamp"],
        "machine_id": df["machine_id"],
        "drift": drift,
        "health_score": score.where(df["is_failed"] == 0, 0.0),
        "status": _debounce(list(raw_status)),
        "top_driver": driver,
    })
    out["_ratio"] = np.exp(ratios.max(axis=1))
    return out


def _rul_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("timestamp").reset_index(drop=True)
    smooth = df[["vib_1x", "vib_band_0_4k", "vib_band_4_8k", "temp_motor",
                 "current", "speed_rpm"]].rolling(9, min_periods=1).median()
    dt = df["timestamp"].diff().dt.total_seconds().clip(upper=10).fillna(0)
    is_5v = (df["regime"] == "5V").astype(int)
    smooth["is_5v"] = is_5v
    smooth["overstress_s"] = (dt * is_5v).cumsum()
    return smooth[RUL_FEATURES]


def _forest() -> RandomForestRegressor:
    return RandomForestRegressor(n_estimators=150, min_samples_leaf=3, random_state=0, n_jobs=-1)


def estimate_rul(readings: pd.DataFrame):
    """Out-of-fold RUL estimates (seconds) for every reading plus evaluation metrics.

    Each block of CV_BLOCK readings is predicted by a model that never saw that
    block or its neighbours, so the replay does not show an in-sample fit.
    Needs the true RUL (rul_true_s) of the run, so it only works on a
    run-to-failure recording.
    """
    df = readings.sort_values("timestamp").reset_index(drop=True)
    ok = (df["is_failed"] == 0).to_numpy()
    X = _rul_features(df)
    y = df["rul_true_s"].to_numpy()
    Xo, yo = X[ok], y[ok]

    block = np.arange(len(Xo)) // CV_BLOCK
    oof = np.zeros(len(Xo))
    for b in np.unique(block):
        train = np.abs(block - b) > 1
        oof[block == b] = _forest().fit(Xo[train], yo[train]).predict(Xo[block == b])

    split = int(len(Xo) * FORWARD_TRAIN_FRACTION)
    fwd = _forest().fit(Xo.iloc[:split], yo[:split]).predict(Xo.iloc[split:])
    metrics = {
        "rul_mae_blocked_cv_s": mean_absolute_error(yo, oof),
        "rul_mae_forward_s": mean_absolute_error(yo[split:], fwd),
        "rul_mae_mean_baseline_s": mean_absolute_error(yo, np.full(len(yo), yo.mean())),
        "rul_mae_mean_baseline_forward_s": mean_absolute_error(
            yo[split:], np.full(len(yo) - split, yo[:split].mean())),
        "n_readings": float(len(Xo)),
    }
    pred = np.zeros(len(df))
    pred[ok] = np.clip(oof, 0, None)
    return pred, metrics


def build_alerts(health: pd.DataFrame) -> pd.DataFrame:
    """One alert each time the status gets worse."""
    rows, prev = [], health["status"].iloc[0]
    for _, r in health.iterrows():
        status = r["status"]
        if STATUS_RANK[status] > STATUS_RANK[prev]:
            if status == "Failed":
                issue, action = FAILED_ISSUE
            else:
                label, action = ISSUES.get(r["top_driver"], ISSUES["vib_band_0_4k"])
                detail = (f", {r['_ratio']:.1f}x the healthy level"
                          if r["top_driver"] != "temp_motor" else "")
                issue = f"{label}{detail}; health {r['health_score']:.0f}/100"
            rows.append({
                "timestamp": r["timestamp"], "machine_id": r["machine_id"],
                "status_level": status, "detected_issue": issue, "suggested_action": action,
            })
        prev = status
    return pd.DataFrame(rows, columns=db_manager.ALERT_COLUMNS)


def analyze(machine_id: str, db_path=None) -> dict:
    """Runs the full analysis for one machine and stores the results in the database."""
    readings = db_manager.get_readings(machine_id, db_path)
    health = compute_health(readings)
    rul_pred, metrics = estimate_rul(readings)
    health["rul_pred_s"] = rul_pred
    alerts = build_alerts(health)

    db_manager.insert_health_bulk(health, db_path)
    if len(alerts):
        db_manager.replace_alerts(alerts, db_path)
    db_manager.save_metrics(metrics, db_path)
    return {"readings": len(readings), "alerts": len(alerts), **metrics}
