"""Work orders: hand an alert over to an external maintenance service.

"Dispatch Work Order" in the dashboard builds a work order from the alert, the asset and the asset's condition
when the alert was raised, sends it as JSON to a webhook and stores it with the outcome of the delivery
(table `work_orders`). Any service that accepts an HTTP POST can receive it: a CMMS or ticketing API, an
automation tool (Power Automate, Zapier, n8n, Node-RED), or a small adapter in front of SAP PM or Maximo.

Configuration comes from environment variables (on Streamlit Cloud: the app's secrets):

    PDM_WORK_ORDER_URL       where to POST the work order (http or https). Not set: orders are stored only.
    PDM_WORK_ORDER_TOKEN     optional; sent as "Authorization: Bearer <token>"
    PDM_WORK_ORDER_TIMEOUT   seconds to wait for the service (default 10)

Every request carries an `Idempotency-Key` header equal to the work order id, which stays the same when an
order is sent again, so the receiving service can drop duplicates. A delivery counts as sent when the service
answers with a 2xx status.
"""
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from . import db, registry

SCHEMA = "pdm.work_order.v1"
PRIORITIES = {"Failed": "urgent", "Critical": "high", "Warning": "medium"}


@dataclass
class WebhookConfig:
    url: str
    token: Optional[str] = None
    timeout: float = 10.0

    @staticmethod
    def from_env(env=None) -> Optional["WebhookConfig"]:
        """Reads PDM_WORK_ORDER_URL, _TOKEN and _TIMEOUT. Returns None when PDM_WORK_ORDER_URL is not set."""
        env = os.environ if env is None else env
        url = (env.get("PDM_WORK_ORDER_URL") or "").strip()
        if not url:
            return None
        return WebhookConfig(url=url, token=env.get("PDM_WORK_ORDER_TOKEN") or None,
                             timeout=float(env.get("PDM_WORK_ORDER_TIMEOUT") or 10))


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")


def _number(value):
    return None if value is None or value != value else round(float(value), 2)      # NaN -> None


def build_payload(alert: dict, work_order_id: str, created_at: str, requested_by: str = None, db_path=None) -> dict:
    """The JSON document sent to the service: the alert, the asset and its condition when the alert was raised."""
    asset = db.get_asset(alert["asset_id"], db_path)
    t = registry.get_type(asset["type_id"])
    health = db.get_health(alert["asset_id"], db_path)
    health = health[health["ts"] <= alert["ts"]]
    h = health.iloc[-1].to_dict() if len(health) else {}
    return {
        "schema": SCHEMA,
        "work_order_id": work_order_id,
        "created_at": created_at,
        "priority": PRIORITIES.get(alert["status_level"], "medium"),
        "requested_by": requested_by,
        "asset": {"asset_id": asset["asset_id"], "name": asset["name"], "type": t.type_id, "type_name": t.name,
                  "site": asset.get("site")},
        "alert": {"alert_id": int(alert["alert_id"]), "raised_at": str(alert["ts"]),
                  "level": alert["status_level"], "detected_issue": alert["detected_issue"],
                  "suggested_action": alert["suggested_action"]},
        "condition": {
            "status": h.get("status"), "health_score": _number(h.get("health_score")),
            "top_driver": h.get("top_driver"), "age": _number(h.get("age")),
            "rul_estimate": _number(h.get("rul_pred")), "rul_low": _number(h.get("rul_low")),
            "rul_high": _number(h.get("rul_high")), "unit": t.age_unit,
        },
    }


def send(payload: dict, cfg: WebhookConfig) -> tuple:
    """POSTs the payload. Returns (delivered, status code or None, start of the answer or the error)."""
    if not cfg.url.lower().startswith(("http://", "https://")):
        return False, None, "PDM_WORK_ORDER_URL must start with http:// or https://"
    request = urllib.request.Request(
        cfg.url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "Idempotency-Key": payload["work_order_id"],
                 "User-Agent": "pdm-dashboard",
                 **({"Authorization": f"Bearer {cfg.token}"} if cfg.token else {})})
    try:
        with urllib.request.urlopen(request, timeout=cfg.timeout) as response:
            return 200 <= response.status < 300, response.status, response.read(500).decode(errors="replace")
    except urllib.error.HTTPError as e:
        return False, e.code, e.read(500).decode(errors="replace") or e.reason
    except (urllib.error.URLError, OSError, ValueError) as e:
        return False, None, str(getattr(e, "reason", e))


def dispatch(alert_id: int, requested_by: str = None, cfg: WebhookConfig = None, env=None, db_path=None) -> dict:
    """Creates the work order of an alert and sends it; returns the stored order.

    An alert has one work order. Dispatching it again re-sends the same order (same id, so the service can
    drop the duplicate), which is how a failed delivery is retried.
    """
    alert = db.get_alert(alert_id, db_path)
    if alert is None:
        raise KeyError(f"no alert {alert_id}")
    cfg = cfg or WebhookConfig.from_env(env)
    existing = get(alert_id, db_path)
    work_order_id = existing["work_order_id"] if existing else f"WO-{alert['asset_id']}-{int(alert_id)}"
    created_at = existing["created_at"] if existing else _now()
    payload = build_payload(alert, work_order_id, str(created_at), requested_by, db_path)
    order = {"work_order_id": work_order_id, "alert_id": int(alert_id), "asset_id": alert["asset_id"],
             "created_at": str(created_at), "priority": payload["priority"], "payload": json.dumps(payload),
             "target": cfg.url if cfg else None, "delivery": "not_configured",
             "response_code": None, "response": None, "sent_at": None}
    if cfg is not None:
        delivered, code, answer = send(payload, cfg)
        order.update(delivery="sent" if delivered else "failed", response_code=code, response=answer,
                     sent_at=_now() if delivered else None)
    db.save_work_order(order, db_path)
    return order


def get(alert_id: int, db_path=None):
    """The work order of an alert, or None."""
    orders = db.get_work_orders(db_path=db_path)
    orders = orders[orders["alert_id"] == int(alert_id)]
    return None if orders.empty else orders.iloc[0].to_dict()
