import pandas as pd
import streamlit as st

import data_source as ds
import utils


def render_kpi_row(current, type_id: str, method: str):
    """Headline metrics of one asset at the reading currently shown."""
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Status", utils.status_label(current["status"]))
    c2.metric("Health index", f"{current['health_score']:.0f} / 100")
    c3.metric("Estimated RUL", ds.format_rul(current["rul_pred"], type_id),
              help=f"Produced by: {method}. See the Model & Data tab for how far to trust it.")
    if pd.notna(current.get("rul_low")) and pd.notna(current.get("rul_high")):
        c3.caption(f"80% range {ds.format_amount(current['rul_low'], type_id)} to "
                   f"{ds.format_rul(current['rul_high'], type_id)}")
    c4.metric("Actual remaining life", ds.format_amount(current["rul_true"], type_id),
              help="Known from the recorded data. Shown only to compare against the estimate.")
    c5.metric("Age", ds.format_amount(current["age"], type_id))
    return c1, c2, c3, c4, c5


def render_fleet_kpis(counts: dict, n_assets: int):
    cols = st.columns(5)
    cols[0].metric("Assets monitored", n_assets)
    for col, status in zip(cols[1:], ["Failed", "Critical", "Warning", "Healthy"]):
        col.metric(utils.status_label(status), counts.get(status, 0))
