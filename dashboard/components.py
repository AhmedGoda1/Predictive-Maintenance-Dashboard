import streamlit as st

from data_source import format_duration

STATUS_ICON = {"Healthy": "🟢", "Warning": "🟡", "Critical": "🔴", "Failed": "⚫"}


def render_kpi_header(current):
    """Top-level metrics for the reading currently shown in the replay."""
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Status", f"{STATUS_ICON.get(current['status'], '')} {current['status']}")
    c2.metric("Health index", f"{current['health_score']:.0f} / 100")
    c3.metric("Estimated RUL", format_duration(current["rul_pred_s"]),
              help="Model estimate of the time until failure (cross-validated, indicative only).")
    c4.metric("Actual time to failure", format_duration(current["rul_true_s"]),
              help="Known from the recorded run. Shown only to compare against the estimate.")
    c5.metric("Motor temperature", f"{current['temp_motor']:.1f} °C")
