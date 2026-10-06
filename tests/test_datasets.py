import numpy as np
import pytest

from pdm.datasets import cmapss, motor
from pdm.datasets.base import store
from pdm import db


def test_motor_run_shape_and_failure_label():
    run = motor.load()
    s = run.series
    assert len(s) == 377 and run.type_id == "brushed_dc_motor"
    assert run.failure_observed and run.failure_age == s["age"].iloc[-2]      # motor died in the last 2 readings
    assert run.rul_true()[-1] == 0 and (np.diff(run.rul_true()) <= 0).all()
    assert set(s["voltage_regime"]) == {3.0, 5.0}
    assert list(run.segments["name"]) == ["01-Start 3V", "02-Change 5V", "03-Re_start 3V", "04-Change 5V"]


def test_motor_regime_follows_phase_not_voltage():
    run = motor.load()
    stopped = run.series[(run.series["voltage"] < motor.FAILED_VOLTAGE) & (run.series["age"] < 1500)]
    assert len(stopped) >= 1 and (stopped["voltage_regime"] == 5.0).all()   # 0 V reading inside a 5 V phase


def test_cmapss_train_engines_run_to_failure():
    runs = cmapss.load("FD001", "train")
    assert len(runs) == 100 and sum(len(r.series) for r in runs) == 20631
    r = runs[0]
    assert r.failure_observed and r.failure_age == r.last_age and r.rul_true()[-1] == 0
    assert r.series.columns[:2].tolist() == ["ts", "age"] and "s11" in r.series and "op1" in r.series


def test_cmapss_test_engines_are_censored_with_known_rul():
    runs = cmapss.load("FD001", "test")
    assert len(runs) == 100 and sum(len(r.series) for r in runs) == 13096
    r = runs[0]
    assert not r.failure_observed and r.failure_age > r.last_age
    assert r.rul_true()[-1] == 112                      # first line of RUL_FD001.txt


def test_cmapss_validates_arguments():
    with pytest.raises(ValueError):
        cmapss.load("FD009")
    with pytest.raises(ValueError):
        cmapss.load("FD001", "val")


def test_store_writes_asset_failure_and_series(tmp_path):
    p = tmp_path / "t.db"
    db.init_db(p)
    run = cmapss.load("FD001", "test", units={1})[0]
    store(run, p)
    assert db.get_asset(run.asset_id, p)["type_id"] == "turbofan_engine"
    assert len(db.get_series(run.asset_id, p)) == len(run.series)
    f = db.get_failure(run.asset_id, p)
    assert f["observed"] == 0 and f["age"] == run.failure_age
