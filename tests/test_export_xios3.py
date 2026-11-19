import importlib.util
import xml.etree.ElementTree as ET

import data_source as ds
from conftest import ROOT
from pdm import db

_spec = importlib.util.spec_from_file_location("export_xios3", ROOT / "scripts" / "export_xios3.py")
export_xios3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(export_xios3)


def test_export_writes_the_documents_the_xios3_app_binds_to(built_db, tmp_path, monkeypatch):
    result = export_xios3.export(tmp_path, points=40, db_path=built_db)
    assert result["assets"] == 21 and result["alerts"] == len(db.get_alerts(db_path=built_db))

    fleet = ET.parse(tmp_path / "fleet.xml").getroot()
    assets = fleet.findall("asset")
    assert len(assets) == 21 and fleet.get("assets") == "21"
    assert [a.get("rank") for a in assets] == [str(i) for i in range(1, 22)]
    counts = {c.get("status"): int(c.get("n")) for c in fleet.find("summary")}
    assert sum(counts.values()) == 21 and counts["Failed"] == 1

    # same priority order as the dashboard's fleet overview
    monkeypatch.setattr(db, "DB_NAME", built_db)
    snap = ds.snapshot(ds.load_fleet(), 1.0)
    assert [a.get("id") for a in assets] == list(snap["asset_id"])

    alerts = ET.parse(tmp_path / "alerts.xml").getroot().findall("alert")
    assert {a.get("priority") for a in alerts} <= {"urgent", "high", "medium"}
    assert all(a.get("assetName") and a.get("issue") for a in alerts)

    for a in assets:
        points = ET.parse(tmp_path / "history" / f"{a.get('id')}.xml").getroot().findall("point")
        assert 2 <= len(points) <= 40
        ages = [float(p.get("age")) for p in points]
        assert ages == sorted(ages)


def test_rul_text_marks_the_model_cap():
    assert export_xios3.rul_text(125.0, "turbofan_engine") == "≥ 125 cycles"
    assert export_xios3.rul_text(47.4, "turbofan_engine") == "47 cycles"
    assert export_xios3.rul_text(600.0, "brushed_dc_motor") == "10.0 min"
    assert export_xios3.rul_text(None, "turbofan_engine") == "n/a"
