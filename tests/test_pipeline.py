import pytest

from pdm import db, health, pipeline


@pytest.fixture
def built(built_db):
    return built_db, None


def test_both_asset_types_loaded(built):
    path, _ = built
    assert len(db.get_series("MTR_01", path)) == 377
    assets = db.list_assets(db_path=path)
    assert set(assets["type_id"]) == {"brushed_dc_motor", "turbofan_engine"}
    assert len(db.list_assets("turbofan_engine", path)) == pipeline.FLEET_SIZE


def test_motor_health_degrades_and_ends_failed(built):
    path, _ = built
    h = db.get_health("MTR_01", path)
    assert len(h) == 377 and h["health_score"].between(0, 100).all()
    assert h["status"].iloc[-1] == "Failed"
    assert h["health_score"].iloc[:50].mean() > h["health_score"].iloc[-60:-2].mean() + 30
    assert (h["method"] == "single_run_experimental").all()


def test_motor_alerts_only_on_escalation(built):
    path, _ = built
    alerts = db.get_alerts("MTR_01", path).sort_values("ts")
    assert len(alerts) >= 1 and alerts["status_level"].iloc[-1] == "Failed"
    assert all(health.STATUS_RANK[s] > 0 for s in alerts["status_level"])
    assert not alerts["detected_issue"].str.contains("estimated RUL").any()     # experimental RUL stays out of alerts


def test_fleet_status_follows_true_remaining_life(built):
    """Held-out engines: the worse the status at the last reading, the less life they really had left."""
    path, _ = built
    last_true = {}
    for a in db.list_assets("turbofan_engine", path)["asset_id"]:
        h = db.get_health(a, path).iloc[-1]
        last_true.setdefault(h["status"], []).append(db.get_failure(a, path)["age"] - h["age"])
    mean = {k: sum(v) / len(v) for k, v in last_true.items()}
    assert mean["Critical"] < mean["Warning"] < mean["Healthy"]


def test_fleet_predictions_have_intervals(built):
    path, _ = built
    h = db.get_health("FD001-test-001", path)
    assert (h["method"] == "learned").all()
    assert (h["rul_low"] <= h["rul_pred"]).all() and (h["rul_pred"] <= h["rul_high"]).all()


def test_model_registry_and_metrics(built):
    path, _ = built
    models = db.get_models(db_path=path).set_index("model_id")
    assert models.loc["turbofan_FD001", "kind"] == "learned"
    assert models.loc["motor_single_run", "kind"] == "single_run_experimental"
    m = db.get_metrics("turbofan_FD001", path)
    assert m["test_rmse"] < m["baseline_constant_rmse"]
    assert "rul_mae_blocked_cv" in db.get_metrics("MTR_01", path)


def test_debounce_ignores_single_blip():
    raw = ["Healthy"] * 5 + ["Critical"] + ["Healthy"] * 5
    assert set(health._debounce(raw)) == {"Healthy"}
    assert health._debounce(["Healthy"] * 3 + ["Critical"] * 4)[-1] == "Critical"
    assert health._debounce(["Healthy", "Healthy", "Failed"])[-1] == "Failed"


def test_first_reading_noise_does_not_set_the_status():
    assert health._debounce(["Warning", "Healthy", "Healthy", "Healthy"]) == ["Healthy"] * 4
    assert health._debounce(["Warning"] * 3)[-1] == "Warning" and health._debounce(["Warning"] * 3)[0] == "Healthy"
