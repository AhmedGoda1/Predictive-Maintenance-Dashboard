import streamlit as st

def render_kpi_header(df_preds):
    """Renders top-level summary metrics across all assets."""
    total_assets = len(df_preds)
    critical_count = len(df_preds[df_preds["status"] == "Critical"])
    warning_count = len(df_preds[df_preds["status"] == "Warning"])
    avg_rul = round(df_preds["rul_days"].mean(), 1)

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Total Monitored Assets", total_assets)
    c2.metric("Critical Risk Assets", critical_count, delta="-1 this week" if critical_count > 0 else "0", delta_color="inverse")
    c3.metric("Warning State Assets", warning_count)
    c4.metric("Avg Fleet RUL", f"{avg_rul} Days")