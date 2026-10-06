import pandas as pd
import pytest

import db_manager as db


@pytest.fixture
def path(tmp_path):
    p = tmp_path / "test.db"
    db.init_db(p)
    db.insert_machine("M1", "Test motor", "Electric Motor", "Line A", db_path=p)
    return p


def test_init_is_idempotent(path):
    db.init_db(path)
    assert len(db.get_machines(path)) == 1


def test_insert_and_read_reading(path):
    db.insert_reading("M1", timestamp="2020-01-01 00:00:00", vib_1x=0.5, temp_motor=40.0, db_path=path)
    db.insert_reading("M1", timestamp="2020-01-01 00:00:05", vib_1x=0.9, temp_motor=55.0, db_path=path)
    df = db.get_recent_readings("M1", limit=10, db_path=path)
    assert list(df["vib_1x"]) == [0.5, 0.9]            # oldest first
    assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])


def test_unknown_column_rejected(path):
    with pytest.raises(ValueError):
        db.insert_reading("M1", bogus=1.0, db_path=path)


def test_bulk_insert(path):
    df = pd.DataFrame({
        "timestamp": pd.date_range("2020-01-01", periods=5, freq="5s"),
        "machine_id": "M1", "vib_1x": [0.1, 0.2, None, 0.4, 0.5], "is_failed": 0,
    })
    assert db.insert_readings_bulk(df, db_path=path) == 5
    out = db.get_readings("M1", path)
    assert len(out) == 5 and out["vib_1x"].isna().sum() == 1


def test_latest_alert(path):
    assert db.get_latest_alert("M1", path) is None
    db.insert_alert("M1", "Warning", "issue A", "do A", timestamp="2020-01-01 00:00:00", db_path=path)
    db.insert_alert("M1", "Critical", "issue B", "do B", timestamp="2020-01-01 00:01:00", db_path=path)
    assert db.get_latest_alert("M1", path)["status_level"] == "Critical"


def test_metrics_roundtrip(path):
    db.save_metrics({"a": 1.5}, path)
    db.save_metrics({"a": 2.5, "b": 3.0}, path)
    assert db.get_metrics(path) == {"a": 2.5, "b": 3.0}
