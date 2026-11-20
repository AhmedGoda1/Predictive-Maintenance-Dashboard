
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from plotly.subplots import make_subplots
from scipy.io import loadmat


# ==================================================
# 1. PATHS AND SENSOR DEFINITIONS
# ==================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_PATH = (
    BASE_DIR
    / "Data_Milling_Machine"
    / "mill.mat"
)

SENSORS = {
    "smcAC": "Spindle Motor AC Current",
    "smcDC": "Spindle Motor DC Current",
    "vib_table": "Table Vibration",
    "vib_spindle": "Spindle Vibration",
    "AE_table": "Table Acoustic Emission",
    "AE_spindle": "Spindle Acoustic Emission",
}

# Coordinated colours for the six sensor channels
SENSOR_COLORS = {
    "smcAC": "#2563EB",       # Blue
    "smcDC": "#38A3D1",       # Light blue
    "vib_table": "#D97706",   # Amber
    "vib_spindle": "#EA7858", # Coral
    "AE_table": "#6366B9",    # Indigo
    "AE_spindle": "#0D9488",  # Teal
}


# ==================================================
# 2. PAGE STYLING
# ==================================================

st.markdown(
    """
    <style>

    .main-header {
        font-size: 2rem;
        font-weight: 750;
        color: #172B43;
        letter-spacing: -0.7px;
        margin-bottom: 3px;
    }

    .section-heading {
        color: #172B43;
        font-weight: 700;
        font-size: 1.15rem;
        margin-bottom: 4px;
    }

    .section-description {
        color: #64748B;
        font-size: 0.88rem;
        margin-bottom: 12px;
    }

    /* Dataset overview KPI cards */

    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 14px;
        margin-top: 12px;
        margin-bottom: 10px;
    }

    .kpi-card {
        position: relative;
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 17px 17px 15px 19px;
        min-height: 112px;
        box-shadow: 0 2px 7px rgba(15, 23, 42, 0.035);
        overflow: hidden;
    }

    .kpi-card::before {
        content: "";
        position: absolute;
        left: 0;
        top: 0;
        bottom: 0;
        width: 4px;
        background: var(--accent);
    }

    .kpi-top {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 11px;
    }

    .kpi-label {
        color: #64748B;
        font-size: 0.78rem;
        font-weight: 600;
        line-height: 1.3;
    }

    .kpi-icon {
        font-size: 1.15rem;
        color: var(--accent);
        background: var(--icon-bg);
        width: 31px;
        height: 31px;
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .kpi-value {
        color: #172B43;
        font-size: 1.65rem;
        font-weight: 750;
        line-height: 1.1;
        letter-spacing: -0.5px;
    }

    /* Selected experiment information */

    .spec-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 17px 18px;
        margin-top: 10px;
        margin-bottom: 12px;
        box-shadow: 0 2px 7px rgba(15, 23, 42, 0.025);
    }

    .spec-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 16px 20px;
    }

    .spec-item {
        min-width: 0;
        border-left: 3px solid #DBEAFE;
        padding-left: 11px;
    }

    .spec-label {
        color: #64748B;
        font-size: 0.75rem;
        font-weight: 600;
        margin-bottom: 5px;
    }

    .spec-value {
        color: #172B43;
        font-size: 1.05rem;
        font-weight: 700;
        overflow-wrap: anywhere;
    }

    /* Responsive layout */

    @media (max-width: 850px) {
        .kpi-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }

        .spec-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
    }

    @media (max-width: 480px) {
        .kpi-grid {
            grid-template-columns: 1fr;
        }

        .spec-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
    }

    </style>
    """,
    unsafe_allow_html=True
)


# ==================================================
# 3. LOAD NASA DATASET
# ==================================================

@st.cache_data
def load_dataset(path):

    matlab_data = loadmat(path)
    experiments = matlab_data["mill"]

    metadata = []
    signal_records = []

    for i in range(experiments.shape[1]):

        record = experiments[0, i]

        def get_value(field):
            return float(
                np.asarray(record[field]).squeeze()
            )

        metadata.append({
            "Experiment": i + 1,
            "Case": get_value("case"),
            "Run": get_value("run"),
            "Tool Wear (VB)": get_value("VB"),
            "Time": get_value("time"),
            "DOC": get_value("DOC"),
            "Feed": get_value("feed"),
            "Material": get_value("material"),
        })

        signals = {}

        for sensor in SENSORS:

            signals[sensor] = np.asarray(
                record[sensor],
                dtype=float
            ).flatten()

        signal_records.append(signals)

    return pd.DataFrame(metadata), signal_records


# ==================================================
# 4. HEADER
# ==================================================

st.markdown(
    '<div class="main-header">Machine Monitoring</div>',
    unsafe_allow_html=True
)

st.caption(
    "Real sensor signal analysis using the NASA "
    "Milling Machine experimental dataset."
)


# ==================================================
# 5. CHECK DATASET
# ==================================================

if not DATA_PATH.exists():

    st.error(f"NASA dataset not found: {DATA_PATH}")
    st.stop()

try:

    metadata, signal_records = load_dataset(
        str(DATA_PATH)
    )

except Exception as error:

    st.error(f"Could not load dataset: {error}")
    st.stop()


# ==================================================
# 6. DATASET OVERVIEW
# ==================================================

st.markdown(
    '<div class="section-heading">Dataset Overview</div>',
    unsafe_allow_html=True
)

total_experiments = len(metadata)

available_wear = (
    metadata["Tool Wear (VB)"].notna().sum()
)

missing_wear = (
    metadata["Tool Wear (VB)"].isna().sum()
)

kpi_cards = [
    {
        "label": "Total Experiments",
        "value": total_experiments,
        "icon": "▦",
        "accent": "#2563EB",
        "icon_bg": "#EFF6FF",
    },
    {
        "label": "Sensor Channels",
        "value": len(SENSORS),
        "icon": "⌁",
        "accent": "#0891B2",
        "icon_bg": "#ECFEFF",
    },
    {
        "label": "Available Wear Values",
        "value": int(available_wear),
        "icon": "✓",
        "accent": "#059669",
        "icon_bg": "#ECFDF5",
    },
    {
        "label": "Missing Wear Values",
        "value": int(missing_wear),
        "icon": "!",
        "accent": "#D97706",
        "icon_bg": "#FFFBEB",
    },
]

kpi_html = '<div class="kpi-grid">'

for card in kpi_cards:

    kpi_html += f"""
    <div class="kpi-card"
         style="--accent:{card['accent']};
                --icon-bg:{card['icon_bg']};">

        <div class="kpi-top">
            <div class="kpi-label">{card['label']}</div>
            <div class="kpi-icon">{card['icon']}</div>
        </div>

        <div class="kpi-value">{card['value']}</div>

    </div>
    """

kpi_html += "</div>"

st.html(kpi_html)

st.divider()


# ==================================================
# 7. EXPERIMENT SELECTION
# ==================================================

st.markdown(
    '<div class="section-heading">Experiment Selection</div>',
    unsafe_allow_html=True
)

selected_index = st.selectbox(
    "Select an experiment",
    range(len(metadata)),
    format_func=lambda i: (
        f"Experiment {i + 1} | "
        f"Case {int(metadata.iloc[i]['Case'])} | "
        f"Run {int(metadata.iloc[i]['Run'])}"
    )
)

selected = metadata.iloc[selected_index]
selected_signals = signal_records[selected_index]


# ==================================================
# 8. SELECTED EXPERIMENT INFORMATION
# ==================================================

st.markdown(
    '<div class="section-heading">'
    'Selected Experiment Information'
    '</div>',
    unsafe_allow_html=True
)

if pd.notna(selected["Tool Wear (VB)"]):
    wear_value = f"{selected['Tool Wear (VB)']:.3f}"
else:
    wear_value = "Not available"

specifications = [
    ("Experiment", int(selected["Experiment"])),
    ("Case", int(selected["Case"])),
    ("Run", int(selected["Run"])),
    ("Measured Tool Wear (VB)", wear_value),
    ("Depth of Cut (DOC)", f"{selected['DOC']:.2f}"),
    ("Feed", f"{selected['Feed']:.2f}"),
    ("Material Code", int(selected["Material"])),
]

spec_html = '<div class="spec-card"><div class="spec-grid">'

for label, value in specifications:

    spec_html += f"""
    <div class="spec-item">
        <div class="spec-label">{label}</div>
        <div class="spec-value">{value}</div>
    </div>
    """

spec_html += "</div></div>"

st.html(spec_html)

st.divider()


# ==================================================
# 9. SENSOR SIGNAL VISUALIZATION
# ==================================================

st.markdown(
    '<div class="section-heading">Machine Sensor Signals</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-description">'
    'Six recorded sensor channels for the selected experiment.'
    '</div>',
    unsafe_allow_html=True
)

fig = make_subplots(
    rows=3,
    cols=2,
    subplot_titles=list(SENSORS.values()),
    vertical_spacing=0.15,
    horizontal_spacing=0.10
)

positions = [
    (1, 1), (1, 2),
    (2, 1), (2, 2),
    (3, 1), (3, 2)
]

for (sensor, title), (row, col) in zip(
    SENSORS.items(),
    positions
):

    values = selected_signals[sensor]

    fig.add_trace(
        go.Scatter(
            x=np.arange(len(values)),
            y=values,
            mode="lines",
            name=title,
            line=dict(
                width=1.15,
                color=SENSOR_COLORS[sensor]
            ),
            showlegend=False,
            hovertemplate=(
                "Sample: %{x}<br>"
                "Amplitude: %{y:.4f}"
                "<extra></extra>"
            )
        ),
        row=row,
        col=col
    )

    fig.update_xaxes(
        title_text="Sample",
        title_font=dict(size=10, color="#64748B"),
        tickfont=dict(size=9, color="#64748B"),
        gridcolor="#EDF1F5",
        zerolinecolor="#CBD5E1",
        row=row,
        col=col
    )

    fig.update_yaxes(
        title_text="Signal Amplitude",
        title_font=dict(size=10, color="#64748B"),
        tickfont=dict(size=9, color="#64748B"),
        gridcolor="#EDF1F5",
        zerolinecolor="#CBD5E1",
        row=row,
        col=col
    )

fig.update_layout(
    height=1000,
    title=dict(
        text="Six Sensor Channels",
        x=0.02,
        xanchor="left",
        font=dict(size=17, color="#172B43")
    ),
    showlegend=False,
    hovermode="closest",
    template="plotly_white",
    margin=dict(
        l=65,
        r=25,
        t=85,
        b=55
    ),
    paper_bgcolor="#FFFFFF",
    plot_bgcolor="#FFFFFF",
    font=dict(
        family="Arial, sans-serif",
        color="#334155"
    )
)

# Improve subplot title appearance
fig.update_annotations(
    font=dict(
        size=12,
        color="#172B43",
        family="Arial, sans-serif"
    )
)

with st.container(border=True):

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={"displaylogo": False}
    )

st.divider()


# ==================================================
# 10. SENSOR STATISTICS
# ==================================================

st.markdown(
    '<div class="section-heading">Sensor Statistical Analysis</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-description">'
    'Statistical summary of the six recorded sensor signals.'
    '</div>',
    unsafe_allow_html=True
)

statistics = []

for sensor, title in SENSORS.items():

    values = selected_signals[sensor]

    statistics.append({
        "Sensor": title,
        "Mean": np.mean(values),
        "Standard Deviation": np.std(values),
        "RMS": np.sqrt(np.mean(values ** 2)),
        "Peak-to-Peak": np.ptp(values),
        "Maximum": np.max(values),
        "Minimum": np.min(values),
    })

stats_df = pd.DataFrame(statistics)

# Format all statistical values to four decimal places
numeric_columns = [
    "Mean",
    "Standard Deviation",
    "RMS",
    "Peak-to-Peak",
    "Maximum",
    "Minimum",
]

formatted_stats = (
    stats_df.style
    .format(
        {column: "{:.4f}" for column in numeric_columns}
    )
    .set_table_styles([
        {
            "selector": "th",
            "props": [
                ("background-color", "#EAF0F7"),
                ("color", "#172B43"),
                ("font-weight", "700"),
                ("border-bottom", "1px solid #CBD5E1"),
            ]
        },
        {
            "selector": "td",
            "props": [
                ("color", "#334155"),
                ("padding", "9px 10px"),
            ]
        },
    ])
)

with st.container(border=True):

    st.dataframe(
        formatted_stats,
        use_container_width=True,
        hide_index=True
    )

st.caption(
    "RMS means Root Mean Square. These statistics describe "
    "the measured signals and are not validated failure limits."
)

st.divider()


# ==================================================
# 11. TOOL WEAR ANALYSIS
# ==================================================

st.markdown(
    '<div class="section-heading">Tool Wear Analysis</div>',
    unsafe_allow_html=True
)

wear_data = metadata.dropna(
    subset=["Tool Wear (VB)"]
).sort_values(
    ["Case", "Run"]
)

if not wear_data.empty:

    wear_fig = go.Figure()

    selected_case = selected["Case"]

    for case, group in wear_data.groupby("Case"):

        is_selected_case = (case == selected_case)

        if is_selected_case:
            line_color = "#2563EB"
            line_width = 3.2
            marker_size = 7
        else:
            line_color = "#CBD5E1"
            line_width = 1.4
            marker_size = 4

        wear_fig.add_trace(
            go.Scatter(
                x=group["Run"],
                y=group["Tool Wear (VB)"],
                mode="lines+markers",
                name=f"Case {int(case)}",
                line=dict(
                    color=line_color,
                    width=line_width
                ),
                marker=dict(
                    color=line_color,
                    size=marker_size
                ),
                opacity=1.0 if is_selected_case else 0.85,
                hovertemplate=(
                    f"Case {int(case)}"
                    "<br>Run: %{x}"
                    "<br>Tool Wear (VB): %{y:.4f}"
                    "<extra></extra>"
                )
            )
        )

    wear_fig.update_layout(
        title=dict(
            text="Measured Tool Wear Across Experiments",
            x=0.02,
            xanchor="left",
            font=dict(size=17, color="#172B43")
        ),
        xaxis_title="Run",
        yaxis_title="Tool Wear (VB)",
        height=560,
        hovermode="x unified",
        template="plotly_white",
        margin=dict(
            l=65,
            r=30,
            t=75,
            b=145
        ),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font=dict(
            family="Arial, sans-serif",
            color="#334155"
        ),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.25,
            xanchor="center",
            x=0.5,
            font=dict(size=10),
            bgcolor="rgba(255,255,255,0)"
        ),
        xaxis=dict(
            gridcolor="#EDF1F5",
            zerolinecolor="#CBD5E1"
        ),
        yaxis=dict(
            gridcolor="#EDF1F5",
            zerolinecolor="#CBD5E1"
        )
    )

    with st.container(border=True):

        st.plotly_chart(
            wear_fig,
            use_container_width=True,
            config={"displaylogo": False}
        )

else:

    st.info("No measured tool-wear values are available.")

st.caption(
    "The selected experiment's case is highlighted in blue. "
    "Other cases are shown in light grey. Only experiments with "
    "recorded tool-wear measurements are included. Missing values "
    "are not treated as zero."
)

st.divider()


# ==================================================
# 12. EXPERIMENT METADATA
# ==================================================

with st.expander("View Complete Experiment Metadata"):

    st.dataframe(
        metadata,
        use_container_width=True,
        hide_index=True
    )


# ==================================================
# 13. FOOTER
# ==================================================

st.caption(
    "Data source: NASA Milling Machine dataset. "
    "Sensor measurements are experimental recordings."
)
