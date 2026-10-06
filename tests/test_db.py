import numpy as np
import pandas as pd
import pytest

from pdm import db, registry


@pytest.fixture
def path(tmp_path):
    p = tmp_path / "test.db"
    db.init_db(p)
    db.upsert_asset("A1", "brushed_dc_motor", "Test motor", site="Line A", source="unit test", db_path=p)
    return p


def _series(n=5, with_nan=False):
    df = pd.DataFrame({
        "ts": pd.date_range("2020-01-01", periods=n, freq="5s"),
        "age": np.arange(n) * 5.0,
        "vib_1x": np.linspace(0.1, 0.5, n),
        "temp_motor": np.linspace(30, 50, n),
    })
    if with_nan:
        df.loc[2, "vib_1x"] = np.nan
    return df


def test_registry_describes_types():
    motor, fan = registry.get_type("brushed_dc_motor"), registry.get_type("turbofan_engine")
    assert motor.age_unit == "s" and fan.age_unit == "cycle"
    assert "vib_1x" in motor.sensor_names and "op1" in fan.condition_names
    assert {c.name for c in motor.health_channels} == {"vib_1x", "vib_band_0_4k", "vib_band_4_8k"}
    with pytest.raises(KeyError):
        registry.get_type("nope")


def test_init_registers_types_and_is_idempotent(path):
    db.init_db(path)
    with db.connect(path) as conn:
        types = {r[0] for r in conn.execute("SELECT type_id FROM asset_types")}
        n_channels = conn.execute("SELECT COUNT(*) FROM channel_defs WHERE type_id='turbofan_engine'").fetchone()[0]
    assert {"brushed_dc_motor", "turbofan_engine"} <= types
    assert n_channels == len(registry.get_type("turbofan_engine").channels)


def test_series_roundtrip_in_long_format(path):
    assert db.insert_series("A1", _series(5, with_nan=True), path) == 5
    out = db.get_series("A1", path)
    assert list(out["age"]) == [0, 5, 10, 15, 20]
    assert out["vib_1x"].isna().tolist() == [False, False, True, False, False]   # missing stays missing
    with db.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM measurements").fetchone()[0] == 9   # NaN not stored


def test_insert_series_replaces_previous(path):
    db.insert_series("A1", _series(5), path)
    db.insert_series("A1", _series(3), path)
    assert len(db.get_series("A1", path)) == 3


def test_new_channel_needs_no_schema_change(path):
    s = _series(3)
    s["brand_new_sensor"] = [1.0, 2.0, 3.0]
    db.insert_series("A1", s, path)
    assert list(db.get_series("A1", path)["brand_new_sensor"]) == [1.0, 2.0, 3.0]


def test_failure_and_segments(path):
    assert db.get_failure("A1", path) is None
    db.set_failure("A1", "2020-01-01 00:01:00", 60.0, observed=False, db_path=path)
    f = db.get_failure("A1", path)
    assert f["age"] == 60.0 and f["observed"] == 0
    seg = pd.DataFrame({"name": ["p1", "p2"], "start_ts": pd.to_datetime(["2020-01-01", "2020-01-02"]),
                        "end_ts": pd.to_datetime(["2020-01-01 12:00", "2020-01-02 12:00"])})
    db.set_segments("A1", seg, path)
    assert list(db.get_segments("A1", path)["name"]) == ["p1", "p2"]


def test_health_and_alerts_roundtrip(path):
    h = pd.DataFrame({"asset_id": "A1", "ts": pd.date_range("2020-01-01", periods=3, freq="5s"),
                      "age": [0.0, 5.0, 10.0], "drift": 0.1, "health_score": 90.0, "status": "Healthy",
                      "top_driver": None, "method": "x", "rul_pred": [30.0, 20.0, np.nan]})
    assert db.save_health(h, path) == 3
    assert db.save_health(h, path) == 3                       # replaces, does not duplicate
    out = db.get_health("A1", path)
    assert len(out) == 3 and out["rul_pred"].isna().tolist() == [False, False, True]

    assert db.get_latest_alert("A1", path) is None
    db.insert_alert("A1", "Warning", "A", "do A", ts="2020-01-01 00:00:00", db_path=path)
    db.insert_alert("A1", "Critical", "B", "do B", ts="2020-01-01 00:01:00", db_path=path)
    assert db.get_latest_alert("A1", path)["status_level"] == "Critical"
    assert db.replace_alerts(pd.DataFrame(columns=db.ALERT_COLUMNS), ["A1"], path) == 0
    assert db.get_alerts("A1", path).empty


def test_models_and_metrics(path):
    db.register_model("m1", "turbofan_engine", "learned", params={"a": 1}, metrics={"rmse": 2.0}, db_path=path)
    assert list(db.get_models("turbofan_engine", path)["model_id"]) == ["m1"]
    db.save_metrics("m1", {"rmse": 1.5}, path)
    db.save_metrics("m1", {"rmse": 2.5, "mae": 1.0}, path)
    assert db.get_metrics("m1", path) == {"rmse": 2.5, "mae": 1.0}
    assert db.get_metrics("other", path) == {}


def test_unknown_asset(path):
    with pytest.raises(KeyError):
        db.get_asset("nope", path)


def _old_schema_db(path):
    """What an earlier deployment of the app left behind."""
    import sqlite3
    conn = sqlite3.connect(path)
    conn.executescript("CREATE TABLE machines (machine_id TEXT PRIMARY KEY, name TEXT);"
                       "CREATE TABLE sensor_readings (id INTEGER PRIMARY KEY, machine_id TEXT);")
    conn.execute("INSERT INTO machines VALUES ('MTR_01', 'Sawmill Main Drive')")
    conn.commit()
    conn.close()


def test_is_current_tells_old_partial_and_complete_databases_apart(tmp_path):
    assert not db.is_current(tmp_path / "missing.db")
    stale = tmp_path / "stale.db"
    _old_schema_db(stale)
    assert not db.is_current(stale)                         # old schema: tables missing, version 0

    p = tmp_path / "new.db"
    db.init_db(p)
    assert not db.is_current(p)                             # schema only, nothing built yet
    db.upsert_asset("A1", "brushed_dc_motor", "x", db_path=p)
    assert not db.is_current(p)                             # data but never stamped: an interrupted build
    db.mark_current(p)
    assert db.is_current(p)


def test_unreadable_file_is_not_current(tmp_path):
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"this is not a sqlite database" * 20)
    assert not db.is_current(junk)
