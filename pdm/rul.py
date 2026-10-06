"""Remaining-useful-life models.

`RulModel` is the asset-type-independent learned model: it needs a fleet of
run-to-failure assets of the same type, uses only causal features (a reading's
features never depend on later readings) and returns a point estimate with a
prediction interval. Operating conditions are handled by normalising each
sensor within its operating regime.

`single_run_estimate` is the experimental fallback used for the DC motor, where
only one run exists. It cannot be validated across assets.
"""
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GroupKFold

from . import registry

NASA_S1, NASA_S2 = 13.0, 10.0   # PHM08 scoring constants: late predictions are penalised harder


# ---------------------------------------------------------------- metrics
def nasa_score(pred, true) -> float:
    """PHM08 asymmetric score (lower is better). d = predicted - true; late (d > 0) costs more."""
    d = np.asarray(pred, float) - np.asarray(true, float)
    return float(np.where(d < 0, np.exp(-d / NASA_S1) - 1, np.exp(d / NASA_S2) - 1).sum())


def point_metrics(pred, true) -> dict:
    pred, true = np.asarray(pred, float), np.asarray(true, float)
    return {
        "rmse": float(np.sqrt(np.mean((pred - true) ** 2))),
        "mae": float(np.mean(np.abs(pred - true))),
        "bias": float(np.mean(pred - true)),
        "nasa_score": nasa_score(pred, true),
        "n": int(len(true)),
    }


# ---------------------------------------------------------------- features
class FeatureBuilder:
    """Causal window features from the sensors of one asset type.

    Per kept sensor: a short rolling mean, a long rolling mean, a rolling standard deviation and
    the change over one window - all on values z-scored within the operating regime - plus the
    asset's age. Sensors that never vary in the training data are dropped.
    """

    def __init__(self, asset_type: registry.AssetType, window: int = 30, short: int = 5, n_regimes: int = 1,
                 random_state: int = 0):
        self.asset_type = asset_type
        self.window, self.short, self.n_regimes, self.random_state = window, short, n_regimes, random_state

    def _regime(self, frame: pd.DataFrame) -> np.ndarray:
        if self.n_regimes <= 1:
            return np.zeros(len(frame), dtype=int)
        cond = (frame[self.cond_cols].to_numpy() - self.cond_mean) / self.cond_std
        return self._kmeans.predict(cond)

    def fit(self, frames) -> "FeatureBuilder":
        t = self.asset_type
        allrows = pd.concat(list(frames), ignore_index=True)
        self.cond_cols = [c for c in t.condition_names if c in allrows]
        if self.n_regimes > 1:
            cond = allrows[self.cond_cols].to_numpy()
            self.cond_mean, self.cond_std = cond.mean(0), np.where(cond.std(0) > 0, cond.std(0), 1.0)
            self._kmeans = KMeans(self.n_regimes, n_init=10, random_state=self.random_state).fit(
                (cond - self.cond_mean) / self.cond_std)
        regime = self._regime(allrows)
        sensors = [s for s in t.sensor_names if s in allrows and allrows[s].std() > 1e-9]
        self.stats = {}
        for r in range(max(self.n_regimes, 1)):
            part = allrows.loc[regime == r, sensors]
            self.stats[r] = (part.mean().to_numpy(), np.where(part.std().to_numpy() > 1e-9, part.std().to_numpy(), 1.0))
        # drop sensors that are constant inside every regime (only noise after normalisation)
        keep = [i for i, s in enumerate(sensors)
                if any(allrows.loc[regime == r, s].std() > 1e-9 for r in self.stats)]
        self.sensors = [sensors[i] for i in keep]
        self.stats = {r: (m[keep], sd[keep]) for r, (m, sd) in self.stats.items()}
        return self

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Features for every row of ONE asset's series (ordered by age)."""
        regime = self._regime(frame)
        raw = frame[self.sensors].to_numpy(dtype=float)
        z = np.empty_like(raw)
        for r, (mean, sd) in self.stats.items():
            m = regime == r
            z[m] = (raw[m] - mean) / sd
        z = pd.DataFrame(z, columns=self.sensors, index=frame.index)
        short = z.rolling(self.short, min_periods=1).mean()
        long = z.rolling(self.window, min_periods=1).mean()
        spread = z.rolling(self.window, min_periods=2).std().fillna(0.0)
        change = (short - short.shift(self.window)).fillna(0.0)
        out = pd.concat([short.add_prefix("z_"), long.add_prefix("m_"), spread.add_prefix("sd_"),
                         change.add_prefix("d_")], axis=1)
        out["age"] = frame["age"].to_numpy()
        return out


# ---------------------------------------------------------------- learned model
def _hgb(**kw) -> HistGradientBoostingRegressor:
    params = dict(max_iter=250, learning_rate=0.06, max_leaf_nodes=24, min_samples_leaf=40,
                  l2_regularization=1.0, random_state=0)
    params.update(kw)
    return HistGradientBoostingRegressor(**params)


@dataclass
class FitReport:
    oof_rmse: float
    oof_mae: float
    conformal_q: float
    n_units: int
    n_rows: int


class RulModel:
    """Fleet-level RUL regressor with a calibrated prediction interval.

    Trained on piecewise-linear targets min(RUL, rul_cap): early in life the exact remaining
    life is not recoverable from the sensors, so the cap keeps the model from chasing noise.
    The interval comes from quantile models whose width is corrected (conformalised quantile
    regression) with residuals of units the models did not see during fitting.
    """

    def __init__(self, type_id: str, rul_cap: float = None, window: int = 30, n_regimes: int = 1,
                 coverage: float = 0.8, cv_folds: int = 5, model_params: dict = None, random_state: int = 0):
        self.type_id = type_id
        self.asset_type = registry.get_type(type_id)
        self.rul_cap = rul_cap if rul_cap is not None else self.asset_type.rul_cap
        if self.rul_cap is None:
            raise ValueError("rul_cap is required (neither given nor set on the asset type)")
        self.window, self.n_regimes, self.coverage = window, n_regimes, coverage
        self.cv_folds, self.random_state = cv_folds, random_state
        self.model_params = {**(model_params or {}), "random_state": random_state}
        self.report = None

    # -- training
    def _design(self, runs):
        X, y, groups = [], [], []
        for i, run in enumerate(runs):
            feats = self.features.transform(run.series)
            X.append(feats)
            y.append(np.minimum(run.rul_true(), self.rul_cap))
            groups.append(np.full(len(feats), i))
        return pd.concat(X, ignore_index=True), np.concatenate(y), np.concatenate(groups)

    def _fit_trio(self, X, y):
        lo_q, hi_q = (1 - self.coverage) / 2, 1 - (1 - self.coverage) / 2
        p = self.model_params
        return (_hgb(**p).fit(X, y),
                _hgb(loss="quantile", quantile=lo_q, **p).fit(X, y),
                _hgb(loss="quantile", quantile=hi_q, **p).fit(X, y))

    def fit(self, runs) -> "RulModel":
        runs = [r for r in runs if r.failure_age is not None]
        if len(runs) < max(self.cv_folds, 2):
            raise ValueError(f"need at least {max(self.cv_folds, 2)} assets with a known failure, got {len(runs)}")
        self.features = FeatureBuilder(self.asset_type, self.window, n_regimes=self.n_regimes,
                                       random_state=self.random_state).fit([r.series for r in runs])
        X, y, groups = self._design(runs)
        oof = np.zeros((len(y), 3))
        for tr, te in GroupKFold(self.cv_folds).split(X, y, groups):
            for j, m in enumerate(self._fit_trio(X.iloc[tr], y[tr])):
                oof[te, j] = m.predict(X.iloc[te])
        point, lo, hi = oof[:, 0], np.minimum(oof[:, 1], oof[:, 2]), np.maximum(oof[:, 1], oof[:, 2])
        scores = np.maximum(lo - y, y - hi)
        n = len(scores)
        level = min(1.0, np.ceil((n + 1) * self.coverage) / n)
        self.conformal_q = float(np.quantile(scores, level))
        self.models = self._fit_trio(X, y)
        self.report = FitReport(
            oof_rmse=float(np.sqrt(np.mean((np.clip(point, 0, self.rul_cap) - y) ** 2))),
            oof_mae=float(mean_absolute_error(y, np.clip(point, 0, self.rul_cap))),
            conformal_q=self.conformal_q, n_units=len(runs), n_rows=n,
        )
        return self

    # -- inference
    def predict(self, series: pd.DataFrame) -> pd.DataFrame:
        """rul_pred / rul_low / rul_high (age units) for every reading of one asset."""
        X = self.features.transform(series)
        point, lo, hi = (m.predict(X) for m in self.models)
        lo, hi = np.minimum(lo, hi) - self.conformal_q, np.maximum(lo, hi) + self.conformal_q
        point = np.clip(point, 0, self.rul_cap)
        return pd.DataFrame({
            "rul_pred": point,
            "rul_low": np.clip(np.minimum(lo, point), 0, self.rul_cap),
            "rul_high": np.clip(np.maximum(hi, point), 0, self.rul_cap),
        }, index=series.index)

    def save(self, path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path, compress=3)
        return path

    @staticmethod
    def load(path) -> "RulModel":
        return joblib.load(path)


# ---------------------------------------------------------------- evaluation
def evaluate_last_reading(model: RulModel, runs) -> dict:
    """Standard C-MAPSS protocol: predict at the last reading of each (censored) test asset.

    True RUL is not capped, so assets that still have more than the cap left count as errors.
    `coverage` counts an interval whose upper bound reaches the cap as covering any longer true
    remaining life ("at least the cap"); `coverage_strict` does not.
    """
    pred, lo, hi, true = [], [], [], []
    for run in runs:
        out = model.predict(run.series).iloc[-1]
        pred.append(out["rul_pred"]), lo.append(out["rul_low"]), hi.append(out["rul_high"])
        true.append(run.rul_true()[-1])
    pred, lo, hi, true = map(np.asarray, (pred, lo, hi, true))
    m = point_metrics(pred, true)
    m["coverage_strict"] = float(np.mean((true >= lo) & (true <= hi)))
    m["coverage"] = float(np.mean((true >= lo) & ((true <= hi) | (hi >= model.rul_cap))))
    m["mean_interval_width"] = float(np.mean(hi - lo))
    return m


def baseline_metrics(train_runs, test_runs, rul_cap: float, random_state: int = 0) -> dict:
    """Reference points the model has to beat: a constant guess and an age-only model."""
    y_tr = np.concatenate([np.minimum(r.rul_true(), rul_cap) for r in train_runs])
    true = np.array([r.rul_true()[-1] for r in test_runs])
    const = point_metrics(np.full(len(true), y_tr.mean()), true)
    age_tr = np.concatenate([r.series["age"].to_numpy() for r in train_runs]).reshape(-1, 1)
    age_model = _hgb(random_state=random_state).fit(age_tr, y_tr)
    age_pred = np.clip(age_model.predict(np.array([[r.series["age"].iloc[-1]] for r in test_runs])), 0, rul_cap)
    return {"constant": const, "age_only": point_metrics(age_pred, true)}


# ---------------------------------------------------------------- single-run fallback
def single_run_estimate(series: pd.DataFrame, failure_age: float, block: int = 30,
                        smooth: int = 9, random_state: int = 0):
    """EXPERIMENTAL RUL for an asset type with only one recorded run (the DC motor).

    Random forest on smoothed sensors plus accumulated time at the overstress regime. Predictions for
    each block of readings come from a model that never saw that block or its neighbours, so the
    values do not look better than they are. Everything is evaluated on that single run, which does
    not show that the estimate carries over to other assets.
    Returns (rul_pred per reading, metrics dict).
    """
    df = series.sort_values("age").reset_index(drop=True)
    alive = (df["age"] < failure_age).to_numpy()
    y = np.clip(failure_age - df["age"].to_numpy(), 0, None)
    cols = ["vib_1x", "vib_band_0_4k", "vib_band_4_8k", "temp_motor", "current", "speed_rpm"]
    X = df[cols].rolling(smooth, min_periods=1).median()
    dt = df["age"].diff().clip(upper=10).fillna(0.0)
    over = (df["voltage_regime"] > 4).astype(float)
    X["is_5v"], X["overstress_s"] = over, (dt * over).cumsum()
    Xo, yo = X[alive].reset_index(drop=True), y[alive]

    def forest():
        return RandomForestRegressor(150, min_samples_leaf=3, random_state=random_state, n_jobs=-1)

    blocks = np.arange(len(Xo)) // block
    oof = np.zeros(len(Xo))
    for b in np.unique(blocks):
        train = np.abs(blocks - b) > 1
        oof[blocks == b] = forest().fit(Xo[train], yo[train]).predict(Xo[blocks == b])
    split = int(len(Xo) * 0.75)
    fwd = forest().fit(Xo.iloc[:split], yo[:split]).predict(Xo.iloc[split:])
    metrics = {
        "rul_mae_blocked_cv": float(mean_absolute_error(yo, oof)),
        "rul_mae_forward": float(mean_absolute_error(yo[split:], fwd)),
        "rul_mae_mean_baseline": float(mean_absolute_error(yo, np.full(len(yo), yo.mean()))),
        "rul_mae_mean_baseline_forward": float(mean_absolute_error(yo[split:], np.full(len(yo) - split, yo[:split].mean()))),
        "n_readings": float(len(Xo)),
    }
    pred = np.zeros(len(df))
    pred[alive] = np.clip(oof, 0, None)
    return pred, metrics
