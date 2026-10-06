import numpy as np
import pytest

import build_db
import db_manager as db
import health
import ingest


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "pipeline.db"
    result = build_db.build(path)
    return path, result


def test_dataset_shape_and_failure_label():
    df = ingest.load_dataset()
    assert len(df) == 377
    assert df["phase"].notna().all()
    assert df["is_failed"].sum() == 2 and df["is_failed"].iloc[-1] == 1   # motor died at the end
    assert df["rul_true_s"].iloc[-1] == 0
    assert df["rul_true_s"].is_monotonic_decreasing
    assert set(df["regime"]) == {"3V", "5V"}


def test_build_populates_everything(built):
    path, result = built
    assert result["readings_ingested"] == 377
    assert len(db.get_health("MTR_01", path)) == 377
    assert len(db.get_alerts("MTR_01", path)) >= 1
    assert "rul_mae_blocked_cv_s" in db.get_metrics(path)


def test_health_degrades_and_ends_failed(built):
    path, _ = built
    h = db.get_health("MTR_01", path)
    assert h["health_score"].between(0, 100).all()
    assert h["status"].iloc[-1] == "Failed"
    assert h["health_score"].iloc[:50].mean() > h["health_score"].iloc[-60:-2].mean() + 30


def test_alerts_only_on_escalation(built):
    path, _ = built
    alerts = db.get_alerts("MTR_01", path).sort_values("timestamp")
    ranks = [health.STATUS_RANK[s] for s in alerts["status_level"]]
    assert all(r > 0 for r in ranks)
    assert alerts["status_level"].iloc[-1] == "Failed"


def test_rul_beats_baseline_in_cv(built):
    _, result = built
    assert result["rul_mae_blocked_cv_s"] < result["rul_mae_mean_baseline_s"]


def test_debounce_ignores_single_blip():
    raw = ["Healthy"] * 5 + ["Critical"] + ["Healthy"] * 5
    assert set(health._debounce(raw)) == {"Healthy"}
    sustained = ["Healthy"] * 3 + ["Critical"] * 4
    assert health._debounce(sustained)[-1] == "Critical"
    assert health._debounce(["Healthy", "Healthy", "Failed"])[-1] == "Failed"
