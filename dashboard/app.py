import streamlit as st
import pandas as pd

import data_generator as dg
import utils
import components

# Page configuration
st.set_page_config(
    page_title="Predictive Maintenance Dashboard",
    page_icon="🛠️",
    layout="wide"
)

# ---------------------------------------------------------
# Data Layer (Easy to replace with real database connections)
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def load_dashboard_data():
    meta_df = dg.get_asset_metadata()
    telemetry_df = dg.generate_telemetry_data()
    preds_df = dg.generate_ml_predictions()
    return meta_df, telemetry_df, preds_df

meta_df, telemetry_df, preds_df = load_dashboard_data()

# ---------------------------------------------------------
# Sidebar Navigation & Filters
# ---------------------------------------------------------
st.sidebar.title("🛠️ Maintenance Portal")
st.sidebar.markdown("---")

selected_asset_id = st.sidebar.selectbox(
    "Select Asset to Inspect:",
    options=meta_df["asset_id"].tolist()
)

st.sidebar.markdown("---")
st.sidebar.info(
    "**Note:** Currently displaying synthetic telemetry stream. "
    "Connect API endpoint in `data_generator.py` once live backend is ready."
)

# ---------------------------------------------------------
# Main Page Title & Top KPIs
# ---------------------------------------------------------
st.title("Industrial Equipment Health & Analytics")
components.render_kpi_header(preds_df)

st.markdown("---")

# ---------------------------------------------------------
# Tab Layout
# ---------------------------------------------------------
tab_overview, tab_inspector, tab_alerts = st.tabs([
    "📊 Fleet Overview", 
    "🔍 Asset Inspector", 
    "🚨 Active Alerts & Actions"
])

# TAB 1: FLEET OVERVIEW
with tab_overview:
    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.plotly_chart(utils.plot_failure_risk_bar(preds_df), use_container_width=True)

    with col_right:
        st.subheader("Asset Fleet Table")
        merged_summary = pd.merge(meta_df, preds_df, on="asset_id")
        st.dataframe(
            merged_summary[["asset_id", "name", "status", "health_score", "rul_days"]],
            hide_index=True,
            use_container_width=True
        )

# TAB 2: ASSET INSPECTOR
with tab_inspector:
    asset_meta = meta_df[meta_df["asset_id"] == selected_asset_id].iloc[0]
    asset_pred = preds_df[preds_df["asset_id"] == selected_asset_id].iloc[0]

    st.subheader(f"Detailed Inspection: {asset_meta['name']} ({selected_asset_id})")

    # Asset summary cards
    ic1, ic2, ic3 = st.columns([1, 1, 2])
    with ic1:
        st.plotly_chart(utils.plot_health_gauge(asset_pred["health_score"], selected_asset_id), use_container_width=True)
    with ic2:
        st.markdown(f"**Location:** {asset_meta['location']}")
        st.markdown(f"**Equipment Type:** {asset_meta['type']}")
        st.markdown(f"**Predicted RUL:** {asset_pred['rul_days']} Days")
        st.markdown(f"**Status:** `{asset_pred['status']}`")
    with ic3:
        feature_choice = st.selectbox(
            "Select Telemetry Metric:",
            ["temperature_c", "vibration_mm_s", "pressure_psi"]
        )

    # Telemetry plot
    threshold_val = 75.0 if feature_choice == "temperature_c" else None
    st.plotly_chart(
        utils.plot_telemetry_trends(telemetry_df, selected_asset_id, feature=feature_choice, threshold=threshold_val),
        use_container_width=True
    )

# TAB 3: ALERTS & ACTIONS
with tab_alerts:
    st.subheader("Maintenance Dispatch & Alert Log")

    critical_assets = preds_df[preds_df["status"].isin(["Critical", "Warning"])]

    if critical_assets.empty:
        st.success("All assets are operating within healthy parameters.")
    else:
        for _, row in critical_assets.iterrows():
            with st.expander(f"⚠️ Alert: {row['asset_id']} - Status: {row['status']}"):
                st.write(f"**Failure Risk:** {row['failure_prob'] * 100:.1f}%")
                st.write(f"**Estimated Days Until Failure:** {row['rul_days']} days")
                
                c_act1, c_act2 = st.columns([1, 4])
                if c_act1.button(f"Dispatch Work Order", key=f"btn_{row['asset_id']}"):
                    st.success(f"Work order created for {row['asset_id']}. Technician notified.")