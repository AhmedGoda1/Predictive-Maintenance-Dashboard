import numpy as np
import pytest

from pdm import registry, rul
from pdm.datasets import cmapss

FAST = {"max_iter": 40}


@pytest.fixture(scope="module")
def runs():
    return cmapss.load("FD001", "train", units=set(range(1, 21)))


@pytest.fixture(scope="module")
def model(runs):
    return rul.RulModel("turbofan_engine", cv_folds=3, model_params=FAST).fit(runs)


def test_nasa_score_is_asymmetric():
    assert rul.nasa_score([50], [50]) == 0
    early, late = rul.nasa_score([40], [50]), rul.nasa_score([60], [50])
    assert late > early > 0
    assert early == pytest.approx(np.exp(10 / 13) - 1) and late == pytest.approx(np.exp(10 / 10) - 1)


def test_point_metrics():
    m = rul.point_metrics([10, 20], [12, 18])
    assert m["rmse"] == pytest.approx(2.0) and m["mae"] == pytest.approx(2.0) and m["bias"] == 0 and m["n"] == 2


def test_features_are_causal(runs):
    """A reading's features must not change when later readings are removed (no leakage)."""
    fb = rul.FeatureBuilder(registry.get_type("turbofan_engine")).fit([r.series for r in runs])
    s = runs[0].series
    full, cut = fb.transform(s), fb.transform(s.iloc[:80])
    np.testing.assert_allclose(full.iloc[:80].to_numpy(), cut.to_numpy())


def test_constant_sensors_dropped(runs):
    fb = rul.FeatureBuilder(registry.get_type("turbofan_engine")).fit([r.series for r in runs])
    assert "s1" not in fb.sensors and "s11" in fb.sensors      # s1 never varies in FD001


def test_prediction_interval_is_ordered_and_bounded(model, runs):
    out = model.predict(runs[0].series)
    assert len(out) == len(runs[0].series)
    assert (out["rul_low"] <= out["rul_pred"]).all() and (out["rul_pred"] <= out["rul_high"]).all()
    assert out.to_numpy().min() >= 0 and out.to_numpy().max() <= model.rul_cap


def test_model_beats_constant_baseline_on_unseen_engines(model, runs):
    test = cmapss.load("FD001", "test", units=set(range(1, 41)))
    ev = rul.evaluate_last_reading(model, test)
    base = rul.baseline_metrics(runs, test, model.rul_cap)
    assert ev["rmse"] < base["constant"]["rmse"]
    assert 0 <= ev["coverage_strict"] <= ev["coverage"] <= 1


def test_save_and_load_roundtrip(model, runs, tmp_path):
    path = model.save(tmp_path / "m.joblib")
    out = rul.RulModel.load(path).predict(runs[1].series)
    np.testing.assert_allclose(out.to_numpy(), model.predict(runs[1].series).to_numpy())


def test_needs_enough_failed_assets():
    with pytest.raises(ValueError):
        rul.RulModel("turbofan_engine", cv_folds=5).fit(cmapss.load("FD001", "train", units={1, 2}))
    with pytest.raises(ValueError):
        rul.RulModel("brushed_dc_motor")                 # no rul_cap for this type
