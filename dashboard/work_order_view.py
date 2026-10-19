"""The maintenance team's page: the work orders still open, most urgent first, and buttons to report progress.

A technician's Start / Complete / Reject is recorded exactly like a confirmation from the maintenance service
(pdm.work_orders.confirm), so the admin's asset view shows it the same way.
"""
import pandas as pd
import streamlit as st

import data_source as ds
from asset_view import STATUS_ICONS

PRIORITY_ICONS = {"urgent": "⚫", "high": "🔴", "medium": "🟡"}
DELIVERY_TEXT = {"sent": None, "failed": "not delivered to the maintenance service",
                 "not_configured": "stored here only (no maintenance service configured)"}


def _status_text(order) -> str:
    if pd.isna(order["status"]):
        return "🆕 new, not confirmed yet"
    return f"{STATUS_ICONS.get(order['status'], 'ℹ️')} {order['status'].replace('_', ' ')}"


ACTIONS = [("in_progress", "🔧 Start work"), ("completed", "✅ Complete"), ("rejected", "⛔ Reject")]


def _actions(order, user: str) -> None:
    wo_id = order["work_order_id"]
    note = st.text_input("Note (optional)", key=f"note_{wo_id}", max_chars=400,
                         placeholder="What was done, parts used, why it can't be done...")
    for col, (status, label) in zip(st.columns(len(ACTIONS)), ACTIONS):
        if col.button(label, key=f"wo_{status}_{wo_id}", width="stretch", disabled=order["status"] == status):
            ds.confirm_work_order(wo_id, status, note, user)
            st.session_state.pop(f"note_{wo_id}", None)
            st.session_state["wo_done"] = f"{wo_id}: {status.replace('_', ' ')}"
            st.rerun()


def _order(order, user: str) -> None:
    d = order["details"]
    asset, alert, cond = d["asset"], d["alert"], d["condition"]
    title = (f"{PRIORITY_ICONS.get(order['priority'], '⚪')} {order['priority'].capitalize()} · "
             f"{asset['name']} ({asset['asset_id']}) · {alert['detected_issue']}")
    with st.container(border=True):
        st.markdown(f"**{title}**")
        info = [f"Work order **{order['work_order_id']}**", f"created {order['created_at']:%Y-%m-%d %H:%M} UTC",
                _status_text(order)]
        if pd.notna(order.get("external_id")):
            info.append(f"service id **{order['external_id']}**")
        st.caption(" · ".join(info))
        st.write(f"**Suggested action:** {alert['suggested_action']}")
        health = "n/a" if cond["health_score"] is None else f"{cond['health_score']:.0f}/100"
        facts = [f"Alert level **{alert['level']}**", f"health **{health}**",
                 f"estimated RUL **{ds.format_rul(cond['rul_estimate'], asset['type'])}**"]
        if asset.get("site"):
            facts.append(f"site **{asset['site']}**")
        st.markdown(" · ".join(facts) + " (when the alert was raised)")
        if pd.notna(order.get("status_note")):
            st.caption(f"Last note ({order['status_at']:%Y-%m-%d %H:%M} UTC): {order['status_note']}")
        if DELIVERY_TEXT.get(order["delivery"]):
            st.caption(f"⚠️ This order was {DELIVERY_TEXT[order['delivery']]}.")
        _actions(order, user)


def render(user: str = None) -> None:
    st.title("🔧 Open work orders")
    if "wo_done" in st.session_state:
        st.toast(f"Recorded {st.session_state.pop('wo_done')}", icon="✅")
    orders = ds.active_work_orders()
    counts = orders["priority"].value_counts()
    st.markdown(f"**{len(orders)} open** · " + " · ".join(
        f"{icon} {int(counts.get(priority, 0))} {priority}" for priority, icon in PRIORITY_ICONS.items()))
    if orders.empty:
        st.success("No open work orders. Nothing to do right now.")
        return
    st.caption("Most urgent first, then oldest first. An order leaves this list once it is completed, cancelled or "
               "rejected, here or in the maintenance service.")
    for _, order in orders.iterrows():
        _order(order, user)
