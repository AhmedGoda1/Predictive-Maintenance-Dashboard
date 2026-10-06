import time

import pandas as pd
import streamlit as st

import components
import data_source
import utils

# Page configuration
st.set_page_config(
    page_title="Predictive Maintenance Dashboard",
    page_icon="🛠️",
    layout="wide"
)

# ---------------------------------------------------------
# Data layer: SQLite database built from the open DC-motor dataset
# ---------------------------------------------------------
@st.cache_data(show_spinner="Preparing database...")
def load_data():
    return data_source.load_machine_data()


machine, data, alerts_df, metrics = load_data()
n_readings = len(data)
x_range = [data["timestamp"].min(), data["timestamp"].max()]

# ---------------------------------------------------------
# Sidebar: replay of the recorded run as a live stream
# ---------------------------------------------------------
st.sidebar.title("🛠️ Maintenance Portal")
st.sidebar.markdown("---")
st.sidebar.markdown(f"**{machine['name']}**  \n`{machine.name}` · {machine['location']}")

st.session_state.setdefault("pos", n_readings)
st.session_state.setdefault("playing", False)

play_col, reset_col = st.sidebar.columns(2)
if play_col.button("⏸ Pause" if st.session_state.playing else "▶ Play", width="stretch"):
    st.session_state.playing = not st.session_state.playing
    if st.session_state.playing and st.session_state.pos >= n_readings:
        st.session_state.pos = 1
if reset_col.button("⏮ Reset", width="stretch"):
    st.session_state.playing = False
    st.session_state.pos = 1

step = st.sidebar.select_slider("Replay speed (readings per tick)", options=[1, 2, 5, 10], value=5)
if st.session_state.playing:
    st.session_state.pos = min(n_readings, st.session_state.pos + step)
    if st.session_state.pos >= n_readings:
        st.session_state.playing = False

st.sidebar.slider("Replay position (reading #)", 1, n_readings, key="pos")

seen = data.iloc[: st.session_state.pos]
current = seen.iloc[-1]

st.sidebar.markdown("---")
st.sidebar.info(
    "The recorded run of one motor is replayed as if it were a live sensor stream. "
    "Drag the slider or press Play to move through time."
)

# ---------------------------------------------------------
# Main Page Title & Top KPIs
# ---------------------------------------------------------
st.title("Brushed DC Motor Health & Predictive Maintenance")
st.caption(f"Replay time: {current['timestamp']:%Y-%m-%d %H:%M:%S} · "
           f"supply regime: {current['regime']} · phase: {current['phase']}")
components.render_kpi_header(current)

st.markdown("---")

# ---------------------------------------------------------
# Tab Layout
# ---------------------------------------------------------
tab_overview, tab_inspector, tab_alerts, tab_model = st.tabs([
    "📊 Health Overview",
    "🔍 Sensor Inspector",
    "🚨 Active Alerts & Actions",
    "🧠 Model & Data",
])

# TAB 1: HEALTH OVERVIEW
with tab_overview:
    col_left, col_right = st.columns([3, 1])
    with col_left:
        st.plotly_chart(utils.plot_health_timeline(seen, x_range), width="stretch")
    with col_right:
        st.plotly_chart(utils.plot_health_gauge(current["health_score"], current["status"]),
                        width="stretch")
    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.plotly_chart(utils.plot_rul(seen, x_range), width="stretch")
    with col_b:
        st.plotly_chart(utils.plot_status_counts(seen), width="stretch")

# TAB 2: SENSOR INSPECTOR
with tab_inspector:
    feature = st.selectbox(
        "Select sensor:", list(utils.SENSOR_LABELS), format_func=utils.SENSOR_LABELS.get
    )
    st.plotly_chart(utils.plot_sensor(seen, feature, x_range), width="stretch")
    st.caption("Grey shading marks the periods the motor was driven at 5 V (overstress); "
               "the nominal supply is 3 V.")
    with st.expander("Latest readings"):
        cols = ["timestamp", "regime", "speed_rpm", "current", "voltage", "temp_motor",
                "vib_1x", "vib_band_0_4k", "vib_band_4_8k", "health_score", "status"]
        st.dataframe(seen[cols].tail(15).iloc[::-1], hide_index=True, width="stretch")

# TAB 3: ALERTS & ACTIONS
with tab_alerts:
    st.subheader("Maintenance Dispatch & Alert Log")
    active = alerts_df[alerts_df["timestamp"] <= current["timestamp"]]

    if active.empty:
        st.success("No alerts so far. The motor is operating within healthy parameters.")
    else:
        for _, row in active.iterrows():
            icon = components.STATUS_ICON.get(row["status_level"], "⚠️")
            with st.expander(f"{icon} {row['timestamp']:%H:%M:%S} · {row['status_level']} · "
                             f"{row['detected_issue']}", expanded=row["alert_id"] == active.iloc[0]["alert_id"]):
                st.write(f"**Detected issue:** {row['detected_issue']}")
                st.write(f"**Suggested action:** {row['suggested_action']}")
                if st.button("Dispatch Work Order", key=f"btn_{row['alert_id']}"):
                    st.success(f"Work order created for {machine.name}. Technician notified.")

# TAB 4: MODEL & DATA
with tab_model:
    st.subheader("How the numbers are produced")
    st.markdown(
        "- **Health index** compares vibration (1x harmonic, 0-4 kHz and 4-8 kHz bands) with a healthy "
        "baseline taken from the first readings at the same supply voltage, then maps the deviation to 0-100.\n"
        "- **Status** is Healthy ≥ 70, Warning ≥ 40, Critical below that, or from motor temperature "
        "(≥ 60 °C warning, ≥ 70 °C critical). A status change must hold for 3 readings.\n"
        "- **Estimated RUL** comes from a random forest on smoothed sensor features and accumulated "
        "time at 5 V. Estimates shown in the replay are out-of-fold, so the model never saw the block it predicts."
    )
    st.subheader("Evaluation of the RUL estimate (mean absolute error)")
    mae = pd.DataFrame({
        "Evaluation": ["Blocked cross-validation", "Forward in time (train first 75%, test last 25%)"],
        "Model": [metrics["rul_mae_blocked_cv_s"], metrics["rul_mae_forward_s"]],
        "Always predict the training mean": [metrics["rul_mae_mean_baseline_s"],
                                             metrics["rul_mae_mean_baseline_forward_s"]],
    }).set_index("Evaluation")
    st.dataframe(mae.map(lambda s: data_source.format_duration(s)), width="stretch")
    st.warning(
        "**Limitation:** the dataset contains a single motor run to failure. All evaluation is on that one "
        "run, so the RUL estimate is indicative only and is not evidence that the model generalizes to other motors."
    )
    st.subheader("Dataset")
    st.markdown(
        "F.A.I.R. open dataset of brushed DC motor faults for testing of AI algorithms · "
        "[zenodo.org/records/4314249](https://zenodo.org/records/4314249) · licence CC-BY-4.0. "
        "A cheap brushed DC motor was monitored (vibration, current, voltage, temperature) until it failed. "
        "The run has two supply regimes: 3 V (nominal) and 5 V (overstress)."
    )

# Auto-advance the replay
if st.session_state.playing:
    time.sleep(0.5)
    st.rerun()
