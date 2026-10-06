import pytest

import data_source as ds
from pdm import db


@pytest.fixture
def fleet(built_db, monkeypatch):
    monkeypatch.setattr(db, "DB_NAME", built_db)
    return ds.load_fleet()


def test_snapshot_is_ordered_by_maintenance_priority(fleet):
    snap = ds.snapshot(fleet, 1.0)
    assert len(snap) == 21
    assert snap["status"].map(ds.STATUS_RANK).is_monotonic_decreasing       # worst status first
    assert snap["asset_id"].iloc[0] == "MTR_01" and snap["status"].iloc[0] == "Failed"
    critical = snap[snap["status"] == "Critical"]
    assert critical["rul_pred"].is_monotonic_increasing                     # shortest remaining life first


def test_snapshot_replays_the_fleet_through_its_life(fleet):
    start, end = ds.snapshot(fleet, 0.0), ds.snapshot(fleet, 1.0)
    assert (start["position"] == 1).all() and (end["position"] == end["n_readings"]).all()
    assert (start["status"] == "Healthy").all() and (start["open_alerts"] == 0).all()
    counts = ds.status_counts(end)
    assert counts["Critical"] > 0 and counts["Failed"] == 1 and sum(counts.values()) == 21
    assert end["open_alerts"].sum() > 0


def test_snapshot_clamps_fraction(fleet):
    assert (ds.snapshot(fleet, 5)["position"] == ds.snapshot(fleet, 1)["position"]).all()
    assert (ds.snapshot(fleet, -1)["position"] == 1).all()


def test_snapshot_status_tracks_true_remaining_life(fleet):
    snap = ds.snapshot(fleet, 1.0)
    engines = snap[snap["type_id"] == "turbofan_engine"]
    mean_true = engines.groupby("status")["rul_true"].mean()
    assert mean_true["Critical"] < mean_true["Warning"] < mean_true["Healthy"]
    assert (engines["rul_low"] <= engines["rul_pred"]).all() and (engines["rul_pred"] <= engines["rul_high"]).all()


def test_units_are_shown_per_asset_type():
    assert ds.format_amount(120, "brushed_dc_motor") == "2 min"           # stored in seconds
    assert ds.format_amount(47, "turbofan_engine") == "47 cycles"
    assert ds.format_amount(float("nan"), "turbofan_engine") == "n/a"
    assert ds.format_amount(None, "turbofan_engine") == "n/a"


def test_rul_at_the_training_cap_reads_as_at_least():
    assert ds.format_rul(125.0, "turbofan_engine") == "≥ 125 cycles"
    assert ds.format_rul(59.0, "turbofan_engine") == "59 cycles"
    assert ds.format_rul(300.0, "brushed_dc_motor") == "5 min"             # no cap for the motor
    assert ds.format_rul(float("nan"), "turbofan_engine") == "n/a"


def test_load_engine_asset(fleet, built_db, monkeypatch):
    a = ds.load_asset("FD001-test-021")
    assert a.method == "Learned model" and a.model["kind"] == "learned" and a.model["model_id"] == "turbofan_FD001"
    assert a.model["metrics"]["test"]["rmse"] > 0
    assert a.data["rul_low_disp"].notna().all()
    assert a.data["rul_true_disp"].iloc[-1] == pytest.approx(a.failure["age"] - a.data["age"].iloc[-1])


def test_load_motor_asset(fleet):
    a = ds.load_asset("MTR_01")
    assert a.method == "Experimental (single run)" and a.model["kind"] == "single_run_experimental"
    assert "rul_mae_forward" in a.model["metrics"]
    assert a.data["rul_low"].isna().all()                                 # no interval without a validated model
    assert a.data["age_disp"].iloc[-1] == pytest.approx(a.data["age"].iloc[-1] / 60)   # minutes


def test_models_table_lists_both_models(fleet):
    table = ds.models_table(fleet).set_index("Model")
    assert set(table.index) == {"motor_single_run", "turbofan_FD001"}
    assert table.loc["turbofan_FD001", "Interval coverage"] == "0.80"
    assert table.loc["motor_single_run", "Test RMSE"] == "n/a"             # nothing to evaluate on held-out assets
