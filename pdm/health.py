"""Health index, status and alerts for any registered asset type.

Layer A (needs no failures): each health channel of the asset type is compared with a healthy
baseline taken from the asset's own first readings (per operating regime, when the type defines
one); the deviations become a 0-100 index. The channels, how they are compared, the limits and the
thresholds all come from the asset type registry.

When a predicted RUL is available (layer C), the status is the worse of the health-index status and
the status implied by the RUL thresholds of the asset type.

A status only changes after it has held for a few consecutive readings.
"""
import numpy as np
import pandas as pd

from . import registry
from .registry import AssetType

DEBOUNCE = 3                # readings a new status must hold before it is adopted
STATUS_RANK = {"Healthy": 0, "Warning": 1, "Critical": 2, "Failed": 3}
RANK_STATUS = {v: k for k, v in STATUS_RANK.items()}


def _debounce(raw: list, n: int = DEBOUNCE) -> list:
    """A status change is adopted only after it has been seen n times in a row ("Failed" at once)."""
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


def _regimes(series: pd.DataFrame, t: AssetType) -> pd.Series:
    if t.regime_channel and t.regime_channel in series:
        return series[t.regime_channel].fillna(-1)
    return pd.Series(0, index=series.index)


def _channel_deviation(series, t: AssetType, smooth: pd.DataFrame, regime: pd.Series, failed: np.ndarray):
    """(DataFrame of per-channel deviation, healthy baselines) for the type's health channels."""
    chans = [c for c in t.health_channels if c.name in series and series[c.name].notna().any()]
    dev = pd.DataFrame(index=series.index, columns=[c.name for c in chans], dtype=float)
    for r in regime.unique():
        in_regime = (regime == r).to_numpy()
        ref = series[in_regime & ~failed].head(t.baseline_readings)
        for c in chans:
            vals = smooth.loc[in_regime, c.name]
            base = ref[c.name].median()
            if c.health == registry.LOG_RATIO_UP:
                dev.loc[in_regime, c.name] = np.log(vals.clip(lower=1e-6) / max(base, 1e-6)).clip(lower=0)
            else:
                spread = max(ref[c.name].std(), 1e-6 * abs(base), 1e-9)
                dev.loc[in_regime, c.name] = (vals - base).abs() / spread
    return dev, chans


def rul_status(rul_pred: np.ndarray, t: AssetType) -> np.ndarray:
    """Status implied by the predicted RUL thresholds of the asset type."""
    out = np.full(len(rul_pred), "Healthy", dtype=object)
    if t.rul_warning is not None:
        out[rul_pred <= t.rul_warning] = "Warning"
    if t.rul_critical is not None:
        out[rul_pred <= t.rul_critical] = "Critical"
    return out


def compute_health(series: pd.DataFrame, asset_type, failure: dict = None, rul: pd.DataFrame = None) -> pd.DataFrame:
    """Per-reading drift, health score, status and driving channel for one asset.

    series: the asset's wide series (ts, age, channels). failure: its failure event (dict with age,
    observed) or None. rul: optional rul_pred / rul_low / rul_high aligned with `series`.
    """
    t = asset_type if isinstance(asset_type, AssetType) else registry.get_type(asset_type)
    df = series.sort_values("age").reset_index(drop=True)
    failed = np.zeros(len(df), dtype=bool)
    if failure and failure.get("observed", True):
        failed = (df["age"] >= failure["age"]).to_numpy()

    channels = [c.name for c in t.health_channels if c.name in df] + [l[0] for l in t.limits if l[0] in df]
    smooth = df[sorted(set(channels))].rolling(t.smooth_window, min_periods=1).median()
    regime = _regimes(df, t)
    dev, chans = _channel_deviation(df, t, smooth, regime, failed)

    drift = dev.mean(axis=1) if len(chans) else pd.Series(0.0, index=df.index)
    score = 100 * np.exp(-drift / t.drift_scale)
    raw = np.where(score >= t.healthy_min, "Healthy",
                   np.where(score >= t.warning_min, "Warning", "Critical")).astype(object)

    for channel, warn, crit in t.limits:
        if channel in smooth:
            raw[((smooth[channel] >= warn).to_numpy()) & (raw == "Healthy")] = "Warning"
            raw[(smooth[channel] >= crit).to_numpy()] = "Critical"
    if rul is not None:
        worse = np.maximum([STATUS_RANK[s] for s in raw],
                           [STATUS_RANK[s] for s in rul_status(rul["rul_pred"].to_numpy(), t)])
        raw = np.array([RANK_STATUS[r] for r in worse], dtype=object)
    raw[failed] = "Failed"

    driver = dev.idxmax(axis=1).where(drift > 0.05, None) if len(chans) else pd.Series(None, index=df.index, dtype=object)
    for channel, warn, _ in t.limits:     # a limit breach with little other deviation is the driver
        if channel in smooth:
            hot = (smooth[channel] >= warn) & (drift < 0.5)
            driver = driver.where(~hot, channel)

    out = pd.DataFrame({
        "ts": df["ts"], "age": df["age"], "drift": drift,
        "health_score": score.where(~failed, 0.0),
        "status": _debounce(list(raw)),
        "top_driver": driver,
    })
    top_dev = dev.max(axis=1) if len(chans) else pd.Series(0.0, index=df.index)
    out["_top_dev"] = top_dev
    if rul is not None:
        out[["rul_pred", "rul_low", "rul_high"]] = rul[["rul_pred", "rul_low", "rul_high"]].to_numpy()
    return out


def build_alerts(asset_id: str, health: pd.DataFrame, asset_type, age_unit: str = None) -> pd.DataFrame:
    """One alert each time the status gets worse, naming the channel that drives it."""
    t = asset_type if isinstance(asset_type, AssetType) else registry.get_type(asset_type)
    unit = age_unit or t.age_unit
    names = {c.name: c for c in t.channels}
    rows, prev = [], health["status"].iloc[0]
    for _, r in health.iterrows():
        status = r["status"]
        if STATUS_RANK[status] > STATUS_RANK[prev]:
            if status == "Failed":
                issue = f"{t.name} stopped working"
                action = "Take the asset out of service and inspect it before restarting"
            else:
                ch = names.get(r["top_driver"])
                issue = ch.issue if ch and ch.issue else (
                    f"{r['top_driver']} deviating from the healthy level" if r["top_driver"]
                    else "Predicted remaining life is low")
                action = ch.action if ch and ch.action else "Schedule an inspection"
                if ch and ch.health == registry.LOG_RATIO_UP:
                    issue += f", {np.exp(r['_top_dev']):.1f}x the healthy level"
                elif ch and ch.health == registry.Z_ABS:
                    issue += f", {r['_top_dev']:.1f} standard deviations away"
                issue += f"; health {r['health_score']:.0f}/100"
                if pd.notna(r.get("rul_pred")) and r.get("method") != "single_run_experimental":
                    issue += f"; estimated RUL {r['rul_pred']:.0f} {unit}"
            rows.append({"asset_id": asset_id, "ts": r["ts"], "status_level": status,
                         "detected_issue": issue, "suggested_action": action})
        prev = status
    return pd.DataFrame(rows, columns=["asset_id", "ts", "status_level", "detected_issue", "suggested_action"])
