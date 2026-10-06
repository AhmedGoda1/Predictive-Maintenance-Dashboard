import threading

import numpy as np
import pandas as pd
import pytest

from pdm import db, health, ingest
from pdm.datasets import cmapss, motor


def engine_rows(unit=21, n=None):
    """Readings of a held-out C-MAPSS engine in the shape a gateway would send them."""
    run = cmapss.load("FD001", "test", units={unit})[0]
    cols = [c for c in run.series.columns if c not in ("ts", "age")]
    rows = [{"ts": r["ts"].isoformat(), "age": r["age"], "values": {c: float(r[c]) for c in cols}}
            for _, r in run.series.iterrows()]
    return (rows[:n] if n else rows), run


@pytest.fixture
def engine(live_db):
    ingest.register_asset("E1", "turbofan_engine", "Engine 1", source="NASA C-MAPSS FD001", db_path=live_db)
    return live_db


# ---------------------------------------------------------------- assets
def test_register_asset_is_idempotent_and_guards_the_type(live_db):
    a = ingest.register_asset("A1", "brushed_dc_motor", "Motor", site="Line A", db_path=live_db)
    assert a["name"] == "Motor" and a["site"] == "Line A"
    assert ingest.register_asset("A1", "brushed_dc_motor", "other name", db_path=live_db)["name"] == "Motor"
    with pytest.raises(ingest.Conflict):
        ingest.register_asset("A1", "turbofan_engine", db_path=live_db)
    with pytest.raises(ingest.IngestError, match="Unknown asset type"):
        ingest.register_asset("A2", "toaster", db_path=live_db)
    with pytest.raises(ingest.IngestError):
        ingest.register_asset("  ", "brushed_dc_motor", db_path=live_db)


def test_unknown_asset_and_bad_requests(engine):
    with pytest.raises(ingest.NotFound):
        ingest.ingest_readings("nope", [{"ts": "2024-01-01", "values": {"s2": 1.0}, "age": 1}], db_path=engine)
    with pytest.raises(ingest.IngestError):
        ingest.ingest_readings("E1", [], db_path=engine)
    with pytest.raises(ingest.IngestError, match="at most"):
        ingest.ingest_readings("E1", [{}] * (ingest.MAX_BATCH + 1), db_path=engine)


# ---------------------------------------------------------------- validation
@pytest.mark.parametrize("reading, reason", [
    ({"ts": "2024-01-01", "age": 1, "values": {"nonsense": 1.0}}, "unknown channel"),
    ({"ts": "2024-01-01", "age": 1, "values": {"s2": float("nan")}}, "finite"),
    ({"ts": "2024-01-01", "age": 1, "values": {"s2": float("inf")}}, "finite"),
    ({"ts": "2024-01-01", "age": 1, "values": {"s2": True}}, "must be a number"),
    ({"ts": "2024-01-01", "age": 1, "values": {"s2": "12"}}, "must be a number"),
    ({"ts": "2024-01-01", "age": 1, "values": {}}, "non-empty"),
    ({"ts": "2024-01-01", "age": 1}, "non-empty"),
    ({"ts": "not a time", "age": 1, "values": {"s2": 1.0}}, "not a valid timestamp"),
    ({"age": 1, "values": {"s2": 1.0}}, "ts"),
    ({"ts": "2024-01-01", "values": {"s2": 1.0}}, "age is required"),
    ({"ts": "2024-01-01", "age": -3, "values": {"s2": 1.0}}, "negative"),
    ("not an object", "must be an object"),
])
def test_invalid_readings_are_rejected_with_a_reason(engine, reading, reason):
    r = ingest.ingest_readings("E1", [reading], db_path=engine)
    assert (r.accepted, r.rejected) == (0, 1) and reason in r.results[0].reason
    assert db.get_series("E1", engine).empty


def test_valid_readings_in_a_mixed_batch_are_kept(engine):
    rows, _ = engine_rows(n=3)
    batch = [rows[0], {"ts": "2024-01-01", "age": 1, "values": {"nonsense": 1}}, rows[1], rows[2]]
    r = ingest.ingest_readings("E1", batch, db_path=engine)
    assert (r.accepted, r.rejected) == (3, 1)
    assert [x["index"] for x in r.to_dict()["rejected"]] == [1]
    assert len(db.get_series("E1", engine)) == 3


def test_resending_a_batch_is_harmless(engine):
    rows, _ = engine_rows(n=30)
    first = ingest.ingest_readings("E1", rows, db_path=engine)
    again = ingest.ingest_readings("E1", rows, db_path=engine)
    assert first.accepted == 30 and (again.accepted, again.duplicates, again.rejected) == (0, 30, 0)
    assert len(db.get_series("E1", engine)) == 30


def test_out_of_order_and_non_increasing_age_are_rejected(engine):
    rows, _ = engine_rows(n=10)
    ingest.ingest_readings("E1", rows[5:], db_path=engine)
    r = ingest.ingest_readings("E1", [rows[2]], db_path=engine)                  # older than the newest
    assert r.rejected == 1 and "out of order" in r.results[0].reason
    later = {**rows[-1], "ts": "2030-01-01T00:00:00", "age": rows[-1]["age"]}    # newer, but the age did not advance
    r = ingest.ingest_readings("E1", [later], db_path=engine)
    assert r.rejected == 1 and "age must increase" in r.results[0].reason


def test_batch_is_ordered_by_time_before_it_is_stored(engine):
    rows, _ = engine_rows(n=25)
    r = ingest.ingest_readings("E1", rows[::-1], db_path=engine)                 # newest first
    assert r.accepted == 25 and list(db.get_series("E1", engine)["age"]) == [x["age"] for x in rows]


def test_timestamps_with_a_timezone_are_stored_as_utc(engine):
    row = {"ts": "2024-05-01T12:00:00+02:00", "age": 1, "values": {"s2": 642.0}}
    ingest.ingest_readings("E1", [row], db_path=engine)
    assert db.get_series("E1", engine)["ts"].iloc[0] == pd.Timestamp("2024-05-01 10:00:00")


# ---------------------------------------------------------------- types measured in seconds
def test_age_is_derived_from_time_for_second_based_types_and_the_regime_carries_forward(live_db):
    ingest.register_asset("M1", "brushed_dc_motor", db_path=live_db)
    first = {"ts": "2024-01-01T00:00:00", "values": {"vib_1x": 0.1, "temp_motor": 30.0}}
    r = ingest.ingest_readings("M1", [first], db_path=live_db)
    assert r.rejected == 1 and "voltage_regime is required" in r.results[0].reason       # nothing to carry yet

    first["values"]["voltage_regime"] = 3.0
    second = {"ts": "2024-01-01T00:00:10", "values": {"vib_1x": 0.2, "temp_motor": 31.0}}
    ingest.ingest_readings("M1", [first, second], db_path=live_db)
    s = db.get_series("M1", live_db)
    assert list(s["age"]) == [0.0, 10.0] and list(s["voltage_regime"]) == [3.0, 3.0]


# ---------------------------------------------------------------- scoring
def test_asset_learns_its_baseline_before_it_is_scored(engine):
    rows, _ = engine_rows(n=25)
    early = ingest.ingest_readings("E1", rows[:10], db_path=engine)
    assert early.state["status"] == "Learning" and early.state["readings_needed"] == 20
    assert db.get_health("E1", engine).empty and db.get_alerts("E1", engine).empty
    later = ingest.ingest_readings("E1", rows[10:], db_path=engine)
    assert later.state["status"] == "Healthy" and later.state["method"] == "learned"
    assert len(db.get_health("E1", engine)) == 25


def test_live_scoring_gives_the_same_result_as_scoring_the_stored_history(engine):
    rows, run = engine_rows()
    for i in range(0, len(rows), 7):
        ingest.ingest_readings("E1", rows[i:i + 7], db_path=engine)
    stored = db.get_health("E1", engine)
    series = db.get_series("E1", engine)
    model = ingest.learned_model_for(db.get_asset("E1", engine), ingest.registry.get_type("turbofan_engine"), engine)
    offline = health.compute_health(series, "turbofan_engine", None, model.predict(series))
    np.testing.assert_allclose(stored["health_score"], offline["health_score"])
    np.testing.assert_allclose(stored["rul_pred"], offline["rul_pred"])
    assert list(stored["status"]) == list(offline["status"])
    assert abs(stored["rul_pred"].iloc[-1] - run.rul_true()[-1]) < 15           # sane against the known truth


def test_alerts_are_added_once_and_keep_their_ids(engine):
    rows, _ = engine_rows()
    ingest.ingest_readings("E1", rows[:135], db_path=engine)               # this engine's first alert comes at cycle 126
    before = db.get_alerts("E1", engine)
    ingest.ingest_readings("E1", rows[135:], db_path=engine)
    after = db.get_alerts("E1", engine)
    assert len(before) >= 1 and len(after) >= len(before)
    assert set(before["alert_id"]) <= set(after["alert_id"])                     # nothing re-created
    assert not after.duplicated(["ts", "status_level"]).any()


def test_reporting_a_failure_marks_the_asset_failed(engine):
    rows, _ = engine_rows(n=40)
    ingest.ingest_readings("E1", rows, db_path=engine)
    with pytest.raises(ingest.IngestError, match="age is required"):
        ingest.report_failure("E1", "2024-01-01", db_path=engine)
    state = ingest.report_failure("E1", rows[-1]["ts"], age=rows[-1]["age"], mode="HPC", db_path=engine)
    assert state["status"] == "Failed" and db.get_failure("E1", engine)["observed"] == 1


def test_a_scoring_failure_does_not_lose_the_data(engine, monkeypatch):
    monkeypatch.setattr(ingest, "score_asset", lambda *a, **k: 1 / 0)
    rows, _ = engine_rows(n=30)
    r = ingest.ingest_readings("E1", rows, db_path=engine)
    assert r.accepted == 30 and "ZeroDivisionError" in r.scoring_error
    assert len(db.get_series("E1", engine)) == 30


def test_concurrent_writers_of_one_asset_do_not_duplicate_or_crash(engine):
    rows, _ = engine_rows(n=50)
    errors = []

    def send():
        try:
            ingest.ingest_readings("E1", rows, db_path=engine)
        except Exception as e:                                                   # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=send) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors and len(db.get_series("E1", engine)) == 50


def test_motor_without_a_learned_model_is_scored_on_health_only(live_db):
    run = motor.load()
    ingest.register_asset("M1", "brushed_dc_motor", source="Zenodo 4314249", db_path=live_db)
    cols = [c for c in run.series.columns if c not in ("ts", "age")]
    rows = [{"ts": r["ts"].isoformat(), "age": r["age"], "values": {c: float(r[c]) for c in cols}}
            for _, r in run.series.iterrows()]
    r = ingest.ingest_readings("M1", rows, db_path=live_db)
    assert r.accepted == 377 and r.state["rul"] is None and r.state["method"] is None
    assert r.state["status"] in ("Healthy", "Warning", "Critical")               # failure not reported yet
    assert ingest.report_failure("M1", rows[-2]["ts"], age=rows[-2]["age"], db_path=live_db)["status"] == "Failed"


def test_two_writers_racing_on_the_same_reading_store_it_once(engine, monkeypatch):
    """Another process stores a reading between our duplicate check and our insert: the database refuses the second
    copy and the retry sees it as the duplicate it is."""
    rows, _ = engine_rows(n=30)
    ingest.ingest_readings("E1", rows, db_path=engine)
    real_seen, real_last = db.existing_timestamps, db.get_last_reading
    calls = {"n": 0}

    def stale_seen(*a, **k):                      # what a writer that looked just before the other one stored sees
        calls["n"] += 1
        return set() if calls["n"] == 1 else real_seen(*a, **k)

    monkeypatch.setattr(db, "existing_timestamps", stale_seen)
    monkeypatch.setattr(db, "get_last_reading", lambda *a, **k: None if calls["n"] == 0 else real_last(*a, **k))
    r = ingest.ingest_readings("E1", rows, db_path=engine)
    assert calls["n"] == 2                        # it did try twice
    assert (r.accepted, r.duplicates, r.rejected) == (0, 30, 0)
    assert len(db.get_series("E1", engine)) == 30


def test_a_device_cannot_claim_to_be_a_recorded_demo_asset(live_db):
    asset = ingest.register_asset("sneaky", "turbofan_engine", metadata={"recorded": True, "split": "train", "live": True},
                                  db_path=live_db)
    assert asset["metadata"] == {"live": True}    # the reserved keys are dropped, other metadata is kept
