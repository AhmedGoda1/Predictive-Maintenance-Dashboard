import importlib.util
import json
import time
from pathlib import Path

import pandas as pd
import pytest

from pdm import db, ingest
from pdm.mqtt_ingest import MqttConfig, MqttIngestor, config_from_options

spec = importlib.util.spec_from_file_location("publish_csv", Path(__file__).resolve().parents[1] / "scripts" / "publish_csv.py")
publish_csv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish_csv)


@pytest.fixture
def log():
    return pd.DataFrame({"time": pd.date_range("2024-05-01 10:00", periods=30, freq="5s"),
                         "temp_c": [40 + i * 0.1 for i in range(30)], "vib_g": [0.10 + i * 0.001 for i in range(30)],
                         "note": ["x"] * 30})


def test_columns_become_channels_and_constants_are_added(log):
    r = publish_csv.build_readings(log, "brushed_dc_motor", "time", {"temp_c": "temp_motor", "vib_g": "vib_1x"},
                                   {"voltage_regime": "3"})
    assert len(r) == 30 and r[0]["values"] == {"voltage_regime": 3.0, "temp_motor": 40.0, "vib_1x": 0.10}
    assert r[0]["ts"].startswith("2024-05-01T10:00:00") and "age" not in r[0]


def test_missing_cells_are_left_out_not_sent_as_nan(log):
    log["vib_g"] = log["vib_g"].astype(object)                  # a CSV column that contains text, as real logs do
    log.loc[2, "temp_c"] = None
    log.loc[3, "vib_g"] = "n/a"
    r = publish_csv.build_readings(log, "brushed_dc_motor", "time", {"temp_c": "temp_motor", "vib_g": "vib_1x"})
    assert "temp_motor" not in r[2]["values"] and "vib_1x" not in r[3]["values"]


def test_cycle_based_types_need_an_age_column():
    df = pd.DataFrame({"t": pd.date_range("2024-01-01", periods=3, freq="h"), "cycle": [1, 2, 3], "x": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError, match="age-column"):
        publish_csv.build_readings(df, "turbofan_engine", "t", {"x": "s2"})
    r = publish_csv.build_readings(df, "turbofan_engine", "t", {"x": "s2"}, age_column="cycle")
    assert [x["age"] for x in r] == [1.0, 2.0, 3.0]


@pytest.mark.parametrize("mapping, consts, message", [
    ({"temp_c": "temperature"}, {}, "not channels of brushed_dc_motor: temperature"),     # a typo in the channel name
    ({"temp_c": "temp_motor"}, {"nonsense": "1"}, "nonsense"),
    ({"temp_celsius": "temp_motor"}, {}, "not in the file: temp_celsius"),
    ({}, {}, "map at least one column"),
])
def test_mistakes_are_explained_before_anything_is_sent(log, mapping, consts, message):
    with pytest.raises(ValueError, match=message):
        publish_csv.build_readings(log, "brushed_dc_motor", "time", mapping, consts)


def test_bad_timestamps_are_reported(log):
    log["time"] = log["time"].astype(str)
    log.loc[4, "time"] = "yesterday-ish"
    with pytest.raises(ValueError, match="not valid timestamps"):
        publish_csv.build_readings(log, "brushed_dc_motor", "time", {"temp_c": "temp_motor"})


def test_now_shifts_the_log_to_the_present_and_keeps_the_spacing(log):
    r = publish_csv.build_readings(log, "brushed_dc_motor", "time", {"temp_c": "temp_motor"}, now=True)
    stamps = pd.to_datetime([x["ts"] for x in r])
    assert stamps.is_monotonic_increasing and (stamps[1:] - stamps[:-1] == pd.Timedelta(seconds=5)).all()
    assert abs((pd.Timestamp.now(tz="UTC") - stamps[-1]).total_seconds()) < 5          # the last reading is "now"


def test_the_published_readings_are_accepted_by_the_ingestion_code(log, live_db):
    ingest.register_asset("press4", "brushed_dc_motor", db_path=live_db)
    r = publish_csv.build_readings(log, "brushed_dc_motor", "time", {"temp_c": "temp_motor", "vib_g": "vib_1x"},
                                   {"voltage_regime": "3"})
    result = ingest.ingest_readings("press4", json.loads(json.dumps(r)), live_db)           # as it arrives: JSON
    assert result.accepted == 30 and result.state["status"] in ("Healthy", "Warning", "Critical")


def test_config_options_override_the_environment():
    env = {"PDM_MQTT_HOST": "from-env", "PDM_MQTT_PORT": "1883", "PDM_MQTT_USERNAME": "env-user"}
    cfg = config_from_options(host="cli-host", port=8883, env=env)
    assert (cfg.host, cfg.port, cfg.username, cfg.tls) == ("cli-host", 8883, "env-user", True)
    assert config_from_options(env={}) is None
    assert config_from_options(host="h", tls=True, env={}).tls is True


def test_command_line_checks_and_errors(log, tmp_path, capsys):
    path = tmp_path / "log.csv"
    log.to_csv(path, index=False)
    base = [str(path), "--asset", "press4", "--type", "brushed_dc_motor", "--ts-column", "time", "--map", "temp_c=temp_motor",
            "--const", "voltage_regime=3"]
    assert publish_csv.main([*base, "--dry-run"]) == 0 and "30 reading(s)" in capsys.readouterr().out
    assert publish_csv.main([*base[:-4], "--map", "temp_c=tempmotor", "--dry-run"]) == 2          # typo in the channel name
    assert "not channels of brushed_dc_motor" in capsys.readouterr().err
    assert publish_csv.main([str(tmp_path / "nope.csv"), *base[1:], "--dry-run"]) == 2
    assert publish_csv.main([*base]) == 2 and "no broker" in capsys.readouterr().err               # no broker configured


def test_publishing_a_csv_through_a_real_broker(log, tmp_path, mqtt_broker, live_db, monkeypatch, capsys):
    monkeypatch.delenv("PDM_MQTT_HOST", raising=False)
    cfg = MqttConfig(mqtt_broker.host, mqtt_broker.port, client_id=f"csv-test-{time.time_ns()}")
    service = MqttIngestor(cfg, live_db).start()
    try:
        path = tmp_path / "log.csv"
        log.to_csv(path, index=False)
        code = publish_csv.main([str(path), "--asset", "press4", "--type", "brushed_dc_motor", "--name", "Press 4 drive",
                                 "--ts-column", "time", "--map", "temp_c=temp_motor", "--map", "vib_g=vib_1x",
                                 "--const", "voltage_regime=3", "--batch", "10", "--host", mqtt_broker.host,
                                 "--port", str(mqtt_broker.port)])
        assert code == 0
        end = time.time() + 20
        while time.time() < end and not (db.asset_exists("press4", live_db) and len(db.get_series("press4", live_db)) == 30):
            time.sleep(0.1)
        assert db.get_asset("press4", live_db)["name"] == "Press 4 drive" and len(db.get_series("press4", live_db)) == 30
        # a second run of the same file is harmless: everything is a duplicate
        assert publish_csv.main([str(path), "--asset", "press4", "--type", "brushed_dc_motor", "--ts-column", "time",
                                 "--map", "temp_c=temp_motor", "--const", "voltage_regime=3", "--host", mqtt_broker.host,
                                 "--port", str(mqtt_broker.port)]) == 0
        time.sleep(1)
        assert len(db.get_series("press4", live_db)) == 30
    finally:
        service.stop()
