"""Exports the pipeline's results as XML documents for the XIOS3 technician app (xios3/).

The XIOS3 app binds its grids and charts straight to XML, so this script turns maintenance.db into a few small
documents that are uploaded to CloudBackend together with the app:

    xios3/data/fleet.xml              one <asset> per asset, in maintenance-priority order (same order as the
                                      dashboard's fleet overview)
    xios3/data/alerts.xml             every alert, newest first, with the asset name and work-order priority
    xios3/data/history/<asset>.xml    health index and RUL over the asset's life, thinned to at most
                                      --points points so the chart stays light

Usage:
    python scripts/export_xios3.py                 # builds maintenance.db first if it is missing
    python scripts/export_xios3.py --out somewhere --points 80

Work orders are not exported: the XIOS3 app creates and updates them itself in the CloudBackend database.
"""
import argparse
import math
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pdm import db, pipeline, registry, work_orders  # noqa: E402

DEFAULT_OUT = ROOT / "xios3" / "data"
STATUS_RANK = {"Learning": -1, "Healthy": 0, "Warning": 1, "Critical": 2, "Failed": 3}
_DISPLAY_UNITS = {"s": (1 / 60, "min"), "cycle": (1.0, "cycles")}


def _num(value, digits: int = 1) -> str:
    """A number as text for an XML attribute; missing values become an empty string."""
    if value is None or (isinstance(value, float) and math.isnan(value)) or pd.isna(value):
        return ""
    return f"{float(value):.{digits}f}"


def _text(value) -> str:
    return "" if value is None or (not isinstance(value, str) and pd.isna(value)) else str(value)


def _display(value, type_id: str) -> tuple:
    """(value in display units, unit label), e.g. seconds -> minutes for the motor."""
    t = registry.get_type(type_id)
    factor, label = _DISPLAY_UNITS.get(t.age_unit, (1.0, t.age_unit))
    if value is None or pd.isna(value):
        return None, label
    return float(value) * factor, label


def rul_text(value, type_id: str) -> str:
    """Remaining life as shown to a technician: '47 cycles', '12.4 min', '≥ 125 cycles' at the model's cap."""
    t = registry.get_type(type_id)
    shown, label = _display(value, type_id)
    if shown is None:
        return "n/a"
    digits = 1 if label == "min" else 0
    if t.rul_cap and value >= t.rul_cap - 1e-6:
        return f"≥ {_display(t.rul_cap, type_id)[0]:.{digits}f} {label}"
    return f"{shown:.{digits}f} {label}"


def fleet_rows(assets: pd.DataFrame, health: pd.DataFrame, alerts: pd.DataFrame) -> list:
    """Latest state of every scored asset, worst status first, then shortest remaining life."""
    rows = []
    for asset_id, h in health.groupby("asset_id", sort=True):
        r = h.sort_values("age").iloc[-1]
        a = assets.loc[asset_id]
        own = alerts[alerts["asset_id"] == asset_id]
        latest = own.iloc[0] if len(own) else None          # db.get_alerts returns newest first
        rows.append({"asset_id": asset_id, "name": a["name"], "type_id": a["type_id"],
                     "type_name": registry.get_type(a["type_id"]).name, "site": _text(a.get("site")),
                     "status": r["status"], "health": r["health_score"], "top_driver": _text(r["top_driver"]),
                     "rul": r["rul_pred"], "rul_low": r["rul_low"], "rul_high": r["rul_high"],
                     "last_ts": r["ts"], "open_alerts": len(own),
                     "latest_level": latest["status_level"] if latest is not None else "",
                     "latest_issue": latest["detected_issue"] if latest is not None else "",
                     "latest_action": latest["suggested_action"] if latest is not None else ""})
    rows.sort(key=lambda x: (-STATUS_RANK.get(x["status"], 0), x["type_id"],
                             x["rul"] if x["rul"] is not None and not pd.isna(x["rul"]) else float("inf"),
                             x["asset_id"]))
    return rows


def fleet_xml(rows: list, exported: str) -> ET.Element:
    root = ET.Element("fleet", exported=exported, assets=str(len(rows)))
    counts = {s: 0 for s in ("Failed", "Critical", "Warning", "Healthy")}
    for rank, x in enumerate(rows, start=1):
        counts[x["status"]] = counts.get(x["status"], 0) + 1
        ET.SubElement(root, "asset", {
            "id": x["asset_id"], "rank": str(rank), "name": x["name"], "type": x["type_id"],
            "typeName": x["type_name"], "site": x["site"], "status": x["status"],
            "health": _num(x["health"], 0), "rul": _num(_display(x["rul"], x["type_id"])[0]),
            "rulText": rul_text(x["rul"], x["type_id"]),
            "rulLow": _num(_display(x["rul_low"], x["type_id"])[0]),
            "rulHigh": _num(_display(x["rul_high"], x["type_id"])[0]),
            "unit": _display(None, x["type_id"])[1], "topDriver": x["top_driver"],
            "lastReading": str(x["last_ts"])[:19], "openAlerts": str(x["open_alerts"]),
            "latestLevel": x["latest_level"], "latestIssue": x["latest_issue"],
            "latestAction": x["latest_action"]})
    summary = ET.SubElement(root, "summary")
    for status, n in counts.items():
        ET.SubElement(summary, "count", status=status, n=str(n))
    return root


def alerts_xml(assets: pd.DataFrame, alerts: pd.DataFrame, exported: str) -> ET.Element:
    root = ET.Element("alerts", exported=exported)
    for _, a in alerts.iterrows():
        ET.SubElement(root, "alert", {
            "id": str(int(a["alert_id"])), "asset": a["asset_id"],
            "assetName": assets.loc[a["asset_id"], "name"] if a["asset_id"] in assets.index else a["asset_id"],
            "raised": str(a["ts"])[:19], "level": a["status_level"],
            "priority": work_orders.PRIORITIES.get(a["status_level"], "medium"),
            "issue": a["detected_issue"], "action": a["suggested_action"]})
    return root


def thin(h: pd.DataFrame, points: int) -> pd.DataFrame:
    """At most `points` evenly spaced rows, always keeping the last one."""
    if len(h) <= points:
        return h
    idx = sorted({round(i * (len(h) - 1) / (points - 1)) for i in range(points)})
    return h.iloc[idx]


def history_xml(asset_id: str, type_id: str, h: pd.DataFrame, points: int) -> ET.Element:
    unit = _display(None, type_id)[1]
    root = ET.Element("history", asset=asset_id, unit=unit)
    # What the XIOS3 <chart> component plots (its docs only say the root carries a <serie> naming what to plot,
    # so this layout is a best guess to check on the first deployment).
    ET.SubElement(root, "serie", name="Health index", select="point", value="@health", label="@age")
    ET.SubElement(root, "axis", x=f"Age ({unit})", y="Health index (0-100)")
    for _, r in thin(h.sort_values("age"), points).iterrows():
        ET.SubElement(root, "point", {
            "age": _num(_display(r["age"], type_id)[0]), "health": _num(r["health_score"]),
            "rul": _num(_display(r["rul_pred"], type_id)[0]), "status": r["status"]})
    return root


def _write(element: ET.Element, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(element)
    ET.ElementTree(element).write(path, encoding="utf-8", xml_declaration=True)


def export(out_dir: Path = DEFAULT_OUT, points: int = 60, db_path=None) -> dict:
    """Writes the XML documents to out_dir. Returns what was written."""
    if not db.has_assets(db_path):
        pipeline.build(db_path=db_path)
    out_dir = Path(out_dir)
    exported = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assets = db.list_assets(db_path=db_path).set_index("asset_id")
    health = db.get_health(db_path=db_path)
    alerts = db.get_alerts(db_path=db_path)

    rows = fleet_rows(assets, health, alerts)
    _write(fleet_xml(rows, exported), out_dir / "fleet.xml")
    _write(alerts_xml(assets, alerts, exported), out_dir / "alerts.xml")
    for asset_id, h in health.groupby("asset_id"):
        _write(history_xml(asset_id, assets.loc[asset_id, "type_id"], h, points),
               out_dir / "history" / f"{asset_id}.xml")
    seed = out_dir / "workorders.xml"            # empty starting document; the app copies it to the user's Documents
    if not seed.exists():
        _write(ET.Element("workorders"), seed)
    return {"assets": len(rows), "alerts": len(alerts), "out": str(out_dir)}


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output folder (default: xios3/data)")
    parser.add_argument("--points", type=int, default=60, help="most points per history chart (default: 60)")
    args = parser.parse_args(argv)
    result = export(args.out, max(args.points, 2))
    print(f"Exported {result['assets']} assets and {result['alerts']} alerts to {result['out']}")


if __name__ == "__main__":
    main()
