
from pathlib import Path
import sys
import html

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

# --------------------------------------------------
# PATHS AND DATABASE
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
FEATURE_PATH = BASE_DIR / "database" / "milling_features.csv"

sys.path.insert(0, str(BASE_DIR))

from modules import maintenance_db

maintenance_db.initialise_database()

# --------------------------------------------------
# PAGE STYLE
# --------------------------------------------------

st.markdown(
    """
    <style>
    .main-header {
        font-size: 2rem;
        font-weight: 750;
        color: #172B43;
        letter-spacing: -0.6px;
        margin-bottom: 3px;
    }

    .page-description {
        color: #64748B;
        font-size: 0.96rem;
        margin-bottom: 20px;
    }

    .section-heading {
        color: #172B43;
        font-size: 1.25rem;
        font-weight: 700;
        margin-top: 8px;
        margin-bottom: 3px;
    }

    .section-description {
        color: #64748B;
        font-size: 0.85rem;
        margin-bottom: 12px;
    }

    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 14px;
        margin: 18px 0 12px 0;
    }

    .kpi-card {
        position: relative;
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 17px 16px 16px 19px;
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
        margin-bottom: 12px;
    }

    .kpi-label {
        color: #64748B;
        font-size: 0.82rem;
        font-weight: 600;
    }

    .kpi-icon {
        width: 29px;
        height: 29px;
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: var(--icon-bg);
        color: var(--accent);
        font-size: 15px;
    }

    .kpi-value {
        color: #172B43;
        font-size: 1.75rem;
        font-weight: 750;
        line-height: 1.1;
        font-variant-numeric: tabular-nums;
    }

    .analytics-summary {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 20px 22px;
        margin-top: 10px;
        box-shadow: 0 2px 7px rgba(15, 23, 42, 0.035);
    }

    .summary-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 24px;
    }

    .summary-column + .summary-column {
        border-left: 1px solid #E2E8F0;
        padding-left: 24px;
    }

    .summary-title {
        color: #172B43;
        font-weight: 700;
        font-size: 1rem;
        margin-bottom: 12px;
    }

    .summary-item {
        color: #475569;
        font-size: 0.9rem;
        padding: 5px 0;
        border-bottom: 1px solid #F1F5F9;
    }

    .summary-item:last-child {
        border-bottom: none;
    }

    .summary-item strong {
        color: #172B43;
        font-weight: 650;
    }

    .completion-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 20px;
        min-height: 350px;
        box-shadow: 0 2px 7px rgba(15, 23, 42, 0.035);
    }

    .completion-label {
        color: #64748B;
        font-size: 0.9rem;
        font-weight: 600;
        margin-bottom: 10px;
    }

    .completion-value {
        color: #172B43;
        font-size: 2.2rem;
        font-weight: 750;
        line-height: 1.2;
        margin-bottom: 20px;
    }

    .progress-track {
        height: 10px;
        width: 100%;
        background: #E9EEF5;
        border-radius: 20px;
        overflow: hidden;
        margin-bottom: 13px;
    }

    .progress-fill {
        height: 100%;
        background: #0D9488;
        border-radius: 20px;
    }

    .completion-caption {
        color: #64748B;
        font-size: 0.85rem;
        margin-top: 8px;
    }

    @media (max-width: 850px) {
        .kpi-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }

        .summary-grid {
            grid-template-columns: 1fr;
        }

        .summary-column + .summary-column {
            border-left: none;
            border-top: 1px solid #E2E8F0;
            padding-left: 0;
            padding-top: 18px;
        }
    }
    </style>
    """,
    unsafe_allow_html=True
)

# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def render_kpi_cards(cards):
    """Display four professional KPI cards."""

    card_html = '<div class="kpi-grid">'

    for card in cards:
        card_html += f"""
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

    card_html += "</div>"

    st.html(card_html)


def style_chart(fig, height=380):
    """Apply consistent styling to Plotly charts."""

    fig.update_layout(
        template="plotly_white",
        height=height,
        font=dict(
            family="Arial, sans-serif",
            color="#334155",
            size=12
        ),
        title=dict(
            font=dict(
                size=16,
                color="#172B43"
            ),
            x=0.02,
            xanchor="left"
        ),
        margin=dict(
            l=45,
            r=35,
            t=65,
            b=65
        ),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        hoverlabel=dict(
            bgcolor="#172B43",
            font_color="#FFFFFF"
        )
    )

    fig.update_xaxes(
        showgrid=False,
        linecolor="#E2E8F0",
        tickfont=dict(color="#64748B")
    )

    fig.update_yaxes(
        showgrid=True,
        gridcolor="#EEF2F7",
        zeroline=False,
        linecolor="#E2E8F0",
        tickfont=dict(color="#64748B")
    )

    return fig


def normalise_status(value):
    """Standardise status labels for chart colours."""
    return str(value).strip().lower()


# --------------------------------------------------
# HEADER
# --------------------------------------------------

st.markdown(
    '<div class="main-header">Lean Manufacturing Analytics</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="page-description">'
    'Explore tool-wear patterns, maintenance alerts '
    'and work-order performance.'
    '</div>',
    unsafe_allow_html=True
)

# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------

if not FEATURE_PATH.exists():
    st.error("Milling feature dataset not found.")
    st.stop()

try:
    feature_df = pd.read_csv(FEATURE_PATH)

    alerts = maintenance_db.get_alerts()
    work_orders = maintenance_db.get_work_orders()

except Exception as error:
    st.error(f"Could not load analytics data: {error}")
    st.stop()

# --------------------------------------------------
# NORMALISE DATAFRAME COLUMN NAMES
# --------------------------------------------------

feature_df.columns = [
    str(column).strip()
    for column in feature_df.columns
]

case_column = next(
    (
        column
        for column in feature_df.columns
        if column.lower() == "case"
    ),
    None
)

if case_column is not None and case_column != "Case":
    feature_df = feature_df.rename(
        columns={case_column: "Case"}
    )

# --------------------------------------------------
# TOOL-WEAR DATA
# --------------------------------------------------

if "VB" not in feature_df.columns:
    st.error("Tool-wear column VB is missing.")
    st.stop()

wear_df = feature_df.copy()

wear_df["VB"] = pd.to_numeric(
    wear_df["VB"],
    errors="coerce"
)

wear_df = wear_df.replace(
    [np.inf, -np.inf],
    np.nan
)

wear_df = wear_df.dropna(
    subset=["VB"]
)

if wear_df.empty:
    st.warning("No valid measured tool-wear data available.")
    st.stop()

# Prototype threshold for analysis
warning_threshold = 0.50

wear_df["Wear Category"] = np.where(
    wear_df["VB"] >= warning_threshold,
    "Threshold Exceeded",
    "Below Threshold"
)

# --------------------------------------------------
# CASE DATA PREPARATION
# --------------------------------------------------

case_wear_df = pd.DataFrame()
case_counts = pd.DataFrame()

if "Case" in wear_df.columns:

    wear_df["Case"] = pd.to_numeric(
        wear_df["Case"],
        errors="coerce"
    )

    case_wear_df = wear_df.dropna(
        subset=["Case", "VB"]
    ).copy()

    if not case_wear_df.empty:

        case_wear_df["Case"] = (
            case_wear_df["Case"].astype(int)
        )

        case_counts = (
            case_wear_df[
                case_wear_df["VB"] >= warning_threshold
            ]
            .groupby("Case")
            .size()
            .reset_index(name="Exceedances")
            .sort_values(
                "Exceedances",
                ascending=False
            )
        )

# --------------------------------------------------
# KPI CALCULATIONS
# --------------------------------------------------

total_experiments = len(feature_df)

valid_wear_records = len(wear_df)

average_wear = wear_df["VB"].mean()

maximum_wear = wear_df["VB"].max()

threshold_exceedances = int(
    (wear_df["VB"] >= warning_threshold).sum()
)

total_alerts = len(alerts)

total_work_orders = len(work_orders)

completed_orders = sum(
    str(order.get("status", "")).strip().lower() == "completed"
    for order in work_orders
)

completion_rate = (
    completed_orders / total_work_orders * 100
    if total_work_orders > 0
    else 0
)

# --------------------------------------------------
# TOP KPI CARDS
# --------------------------------------------------

render_kpi_cards(
    [
        {
            "label": "Experiments",
            "value": f"{total_experiments:,}",
            "icon": "⚙",
            "accent": "#2563EB",
            "icon_bg": "#EFF6FF"
        },
        {
            "label": "Average Tool Wear",
            "value": f"{average_wear:.3f}",
            "icon": "◉",
            "accent": "#0D9488",
            "icon_bg": "#F0FDFA"
        },
        {
            "label": "Threshold Exceedances",
            "value": f"{threshold_exceedances:,}",
            "icon": "▲",
            "accent": "#D97706",
            "icon_bg": "#FFFBEB"
        },
        {
            "label": "Work Orders",
            "value": f"{total_work_orders:,}",
            "icon": "▤",
            "accent": "#6366B9",
            "icon_bg": "#EEF2FF"
        }
    ]
)

st.divider()

# --------------------------------------------------
# TOOL-WEAR DISTRIBUTION
# --------------------------------------------------

st.markdown(
    '<div class="section-heading">Tool-Wear Distribution</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-description">'
    'Distribution of recorded tool-wear measurements '
    'across the available experiments.'
    '</div>',
    unsafe_allow_html=True
)

# No outer container border around Plotly chart

fig_distribution = px.histogram(
    wear_df,
    x="VB",
    nbins=25,
    title="Distribution of Measured Tool Wear",
    labels={
        "VB": "Measured Tool Wear (VB)",
        "count": "Count"
    },
    color_discrete_sequence=["#2563EB"],
    opacity=0.88
)

fig_distribution.update_traces(
    marker_line_color="#FFFFFF",
    marker_line_width=1,
    hovertemplate=(
        "Measured Tool Wear: %{x:.3f}<br>"
        "Count: %{y}<extra></extra>"
    )
)

fig_distribution.add_vline(
    x=warning_threshold,
    line_dash="dash",
    line_color="#D97706",
    line_width=2,
    annotation_text=f"Threshold (VB = {warning_threshold:.2f})",
    annotation_position="top right",
    annotation_font_color="#B45309",
    annotation_font_size=11
)

style_chart(fig_distribution, height=390)

fig_distribution.update_layout(
    bargap=0.08,
    xaxis=dict(
        title="Measured Tool Wear (VB)",
        tickformat=".2f"
    ),
    yaxis=dict(
        title="Count",
        rangemode="tozero"
    )
)

with st.container(border=True):
    st.plotly_chart(
        fig_distribution,
        use_container_width=True,
        config={'displayModeBar': False}
    )

# --------------------------------------------------
# PARETO ANALYSIS
# --------------------------------------------------

st.divider()

st.markdown(
    '<div class="section-heading">'
    'Pareto Analysis: Tool-Wear Exceedances by Case'
    '</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-description">'
    'Ranks experimental cases according to the number '
    'of measurements at or above the prototype threshold.'
    '</div>',
    unsafe_allow_html=True
)

if "Case" not in wear_df.columns:

    st.warning(
        "The feature dataset does not contain a Case column. "
        "The case-based analysis cannot be generated."
    )

elif case_wear_df.empty:

    st.warning(
        "No valid experimental Case values are available "
        "for the case-based analysis."
    )

elif case_counts.empty:

    st.info(
        "No experiments exceeded the selected prototype threshold."
    )

else:

    case_counts["Cumulative Percentage"] = (
        case_counts["Exceedances"].cumsum()
        / case_counts["Exceedances"].sum()
        * 100
    )

    fig_pareto = make_subplots(
        specs=[[{"secondary_y": True}]]
    )

    fig_pareto.add_trace(
        go.Bar(
            x=case_counts["Case"].astype(str),
            y=case_counts["Exceedances"],
            name="Threshold Exceedances",
            marker_color="#0F766E",
            marker_line_color="#115E59",
            marker_line_width=0.5,
            width=0.58,
            text=case_counts["Exceedances"],
            textposition="outside",
            cliponaxis=False,
            hovertemplate=(
                "Case %{x}<br>"
                "Exceedances: %{y}<extra></extra>"
            )
        ),
        secondary_y=False
    )

    fig_pareto.add_trace(
        go.Scatter(
            x=case_counts["Case"].astype(str),
            y=case_counts["Cumulative Percentage"],
            name="Cumulative Percentage",
            mode="lines+markers",
            line=dict(
                color="#D97706",
                width=3
            ),
            marker=dict(
                size=7,
                color="#D97706",
                line=dict(
                    color="#FFFFFF",
                    width=1
                )
            ),
            hovertemplate=(
                "Case %{x}<br>"
                "Cumulative: %{y:.1f}%<extra></extra>"
            )
        ),
        secondary_y=True
    )

    fig_pareto.add_hline(
        y=80,
        line_dash="dash",
        line_color="#DC6262",
        line_width=1.5,
        annotation_text="80% reference",
        annotation_position="top left",
        annotation_font_color="#DC6262",
        secondary_y=True
    )

    fig_pareto.update_layout(
        title="Tool-Wear Threshold Exceedances by Case",
        template="plotly_white",
        height=460,
        margin=dict(
            l=50,
            r=65,
            t=75,
            b=65
        ),
        font=dict(
            family="Arial, sans-serif",
            color="#334155",
            size=12
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0
        ),
        hoverlabel=dict(
            bgcolor="#172B43",
            font_color="#FFFFFF"
        ),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF"
    )

    fig_pareto.update_xaxes(
        title_text="Experimental Case",
        showgrid=False,
        linecolor="#E2E8F0"
    )

    # LEFT AXIS: EXCEEDANCE COUNTS
    fig_pareto.update_yaxes(
        title_text="Number of Exceedances",
        secondary_y=False,
        range=[0, 10],
        dtick=2,
        showgrid=True,
        gridcolor="#EEF2F7",
        rangemode="tozero"
    )

    # RIGHT AXIS: CUMULATIVE PERCENTAGE
    fig_pareto.update_yaxes(
        title_text="Cumulative Percentage",
        secondary_y=True,
        range=[0, 105],
        dtick=20,
        ticksuffix="%",
        showgrid=False
    )

    st.plotly_chart(
    fig_pareto,
    use_container_width=True,
    config={'displayModeBar': False}

    )

    st.caption(
        "This Pareto chart ranks experimental cases by "
        "the number of tool-wear threshold exceedances. "
        "It does not identify machine failure causes "
        "or production losses."
    )

    display_pareto = case_counts.rename(
        columns={
            "Case": "Experimental Case",
            "Exceedances": "Threshold Exceedances"
        }
    ).copy()

    display_pareto["Cumulative Percentage"] = (
        display_pareto["Cumulative Percentage"].round(1)
    )

    st.dataframe(
        display_pareto,
        use_container_width=True,
        hide_index=True
    )

# --------------------------------------------------
# AVERAGE AND MAXIMUM WEAR BY CASE
# --------------------------------------------------

st.divider()

st.markdown(
    '<div class="section-heading">'
    'Tool Wear by Experimental Case'
    '</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-description">'
    'Compares average and maximum recorded tool wear '
    'across experimental cases.'
    '</div>',
    unsafe_allow_html=True
)

if "Case" not in wear_df.columns:

    st.info(
        "Case information is unavailable in the feature dataset."
    )

elif case_wear_df.empty:

    st.info(
        "No valid case and tool-wear records are available."
    )

else:

    case_wear = (
        case_wear_df.groupby("Case")["VB"]
        .agg(
            Average_Wear="mean",
            Maximum_Wear="max"
        )
        .reset_index()
        .sort_values("Case")
    )

    fig_case = go.Figure()

    fig_case.add_trace(
        go.Bar(
            x=case_wear["Case"].astype(str),
            y=case_wear["Average_Wear"],
            name="Average Wear",
            marker_color="#38A3D1",
            width=0.52,
            hovertemplate=(
                "Case %{x}<br>"
                "Average Wear: %{y:.3f}<extra></extra>"
            )
        )
    )

    fig_case.add_trace(
        go.Scatter(
            x=case_wear["Case"].astype(str),
            y=case_wear["Maximum_Wear"],
            name="Maximum Wear",
            mode="lines+markers",
            line=dict(
                color="#D97706",
                width=2.5
            ),
            marker=dict(
                size=7,
                color="#D97706"
            ),
            hovertemplate=(
                "Case %{x}<br>"
                "Maximum Wear: %{y:.3f}<extra></extra>"
            )
        )
    )

    style_chart(
        fig_case,
        height=420
    )

    fig_case.update_layout(
        title="Average and Maximum Tool Wear by Case",
        barmode="group",
        bargap=0.28,
        bargroupgap=0.12,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0
        ),
        xaxis_title="Experimental Case",
        yaxis_title="Measured Tool Wear (VB)"
    )

    st.plotly_chart(
    fig_case,
    use_container_width=True,
    config={'displayModeBar': False}

    )

# --------------------------------------------------
# ALERT ANALYTICS
# --------------------------------------------------

st.divider()

st.markdown(
    '<div class="section-heading">Maintenance Alert Analytics</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-description">'
    'Overview of alert severity and current alert status.'
    '</div>',
    unsafe_allow_html=True
)

if alerts:

    alert_df = pd.DataFrame(alerts)

    if "severity" in alert_df.columns and "status" in alert_df.columns:

        alert_col, status_col = st.columns(2, gap="large")

        with alert_col:

            severity_counts = (
                alert_df["severity"]
                .fillna("Unknown")
                .astype(str)
                .str.strip()
                .value_counts()
                .reset_index()
            )

            severity_counts.columns = [
                "Severity",
                "Count"
            ]

            severity_colors = {
                "Warning": "#D97706",
                "Critical": "#DC6262",
                "Unknown": "#94A3B8"
            }

            pie_colors = [
                severity_colors.get(
                    str(severity).title(),
                    "#94A3B8"
                )
                for severity in severity_counts["Severity"]
            ]

            fig_severity = go.Figure(
                data=[
                    go.Pie(
                        labels=severity_counts["Severity"],
                        values=severity_counts["Count"],
                        hole=0.55,
                        marker=dict(
                            colors=pie_colors,
                            line=dict(
                                color="#FFFFFF",
                                width=3
                            )
                        ),
                        textinfo="percent",
                        textposition="inside",
                        hovertemplate=(
                            "%{label}<br>"
                            "Alerts: %{value}<br>"
                            "%{percent}<extra></extra>"
                        )
                    )
                ]
            )

            fig_severity.update_layout(
                title="Alert Severity Distribution",
                template="plotly_white",
                height=370,
                margin=dict(
                    l=20,
                    r=20,
                    t=65,
                    b=65
                ),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=-0.12,
                    xanchor="center",
                    x=0.5,
                    font=dict(size=11)
                ),
                paper_bgcolor="#FFFFFF"
            )

            st.plotly_chart(
    fig_severity,
    use_container_width=True,
    config={'displayModeBar': False}

            )

        with status_col:

            status_counts = (
                alert_df["status"]
                .fillna("Unknown")
                .astype(str)
                .str.strip()
                .value_counts()
                .reset_index()
            )

            status_counts.columns = [
                "Status",
                "Count"
            ]

            alert_status_colors = {
                "open": "#D97706",
                "acknowledged": "#2563EB",
                "resolved": "#0D9488",
                "closed": "#0D9488"
            }

            alert_bar_colors = [
                alert_status_colors.get(
                    normalise_status(status),
                    "#94A3B8"
                )
                for status in status_counts["Status"]
            ]

            fig_status = go.Figure(
                go.Bar(
                    x=status_counts["Status"],
                    y=status_counts["Count"],
                    marker_color=alert_bar_colors,
                    width=0.48,
                    text=status_counts["Count"],
                    textposition="outside",
                    cliponaxis=False,
                    hovertemplate=(
                        "%{x}<br>"
                        "Alerts: %{y}<extra></extra>"
                    )
                )
            )

            style_chart(
                fig_status,
                height=370
            )

            fig_status.update_layout(
                title="Alert Status Distribution",
                showlegend=False,
                xaxis_title="Alert Status",
                yaxis_title="Number of Alerts",
                bargap=0.55
            )

            st.plotly_chart(
    fig_status,
    use_container_width=True,
    config={'displayModeBar': False}

            )

    else:

        st.warning(
            "Alert records are missing severity or status information."
        )

else:

    st.info(
        "No alert records are available for analysis."
    )

# --------------------------------------------------
# WORK ORDER ANALYTICS
# --------------------------------------------------

st.divider()

st.markdown(
    '<div class="section-heading">Work Order Performance</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-description">'
    'Overview of work-order status and completion progress.'
    '</div>',
    unsafe_allow_html=True
)

if work_orders:

    work_df = pd.DataFrame(work_orders)

    if "status" not in work_df.columns:

        st.warning(
            "Work-order status information is unavailable."
        )

    else:

        status_counts = (
            work_df["status"]
            .fillna("Unknown")
            .astype(str)
            .str.strip()
            .value_counts()
            .reset_index()
        )

        status_counts.columns = [
            "Status",
            "Count"
        ]

        work_col, completion_col = st.columns(
            2,
            gap="large"
        )

        with work_col:

            work_status_colors = {
                "open": "#D97706",
                "in progress": "#2563EB",
                "completed": "#0D9488",
                "cancelled": "#94A3B8"
            }

            work_bar_colors = [
                work_status_colors.get(
                    normalise_status(status),
                    "#94A3B8"
                )
                for status in status_counts["Status"]
            ]

            fig_work_status = go.Figure(
                go.Bar(
                    x=status_counts["Status"],
                    y=status_counts["Count"],
                    marker_color=work_bar_colors,
                    width=0.48,
                    text=status_counts["Count"],
                    textposition="outside",
                    cliponaxis=False,
                    hovertemplate=(
                        "%{x}<br>"
                        "Work Orders: %{y}<extra></extra>"
                    )
                )
            )

            style_chart(
                fig_work_status,
                height=370
            )

            fig_work_status.update_layout(
                title="Work Order Status",
                showlegend=False,
                xaxis_title="Work Order Status",
                yaxis_title="Number of Work Orders",
                bargap=0.55
            )

            st.plotly_chart(
    fig_work_status,
    use_container_width=True,
    config={'displayModeBar': False}

            )

        with completion_col:

            progress_value = max(
                0,
                min(completion_rate, 100)
            )

            progress_width = f"{progress_value:.1f}%"

            st.html(
                f"""
                <div class="completion-card">

                    <div class="completion-label">
                        Work Order Completion Rate
                    </div>

                    <div class="completion-value">
                        {completion_rate:.1f}%
                    </div>

                    <div class="progress-track">
                        <div class="progress-fill"
                             style="width:{progress_width};">
                        </div>
                    </div>

                    <div class="completion-caption">
                        {completed_orders} of {total_work_orders}
                        work orders completed.
                    </div>

                </div>
                """
            )

else:

    st.info(
        "No work orders are available for analysis."
    )

# --------------------------------------------------
# ANALYTICS SUMMARY
# --------------------------------------------------

st.divider()

st.markdown(
    '<div class="section-heading">Analytics Summary</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-description">'
    'Key findings from the available tool-wear and '
    'maintenance records.'
    '</div>',
    unsafe_allow_html=True
)

st.html(
    f"""
    <div class="analytics-summary">

        <div class="summary-grid">

            <div class="summary-column">

                <div class="summary-title">
                    Tool-Wear Findings
                </div>

                <div class="summary-item">
                    Valid measured wear records:
                    <strong>{valid_wear_records}</strong>
                </div>

                <div class="summary-item">
                    Average measured wear:
                    <strong>{average_wear:.3f}</strong>
                </div>

                <div class="summary-item">
                    Maximum measured wear:
                    <strong>{maximum_wear:.3f}</strong>
                </div>

                <div class="summary-item">
                    Threshold exceedances:
                    <strong>{threshold_exceedances}</strong>
                </div>

            </div>

            <div class="summary-column">

                <div class="summary-title">
                    Maintenance Findings
                </div>

                <div class="summary-item">
                    Total alerts:
                    <strong>{total_alerts}</strong>
                </div>

                <div class="summary-item">
                    Total work orders:
                    <strong>{total_work_orders}</strong>
                </div>

                <div class="summary-item">
                    Completed work orders:
                    <strong>{completed_orders}</strong>
                </div>

                <div class="summary-item">
                    Work order completion rate:
                    <strong>{completion_rate:.1f}%</strong>
                </div>

            </div>

        </div>

    </div>
    """
)

# --------------------------------------------------
# DATASET LIMITATIONS
# --------------------------------------------------

st.warning(
    "Dataset limitation: The NASA milling dataset does not "
    "provide machine downtime, repair duration, maintenance "
    "cost or production-loss information. Therefore, this "
    "dashboard does not calculate MTTR, downtime reduction "
    "or maintenance cost savings."
)

st.caption(
    "The threshold of 0.50 is a prototype analysis setting, "
    "not a validated industrial maintenance limit. "
    "Pareto results describe experimental tool-wear "
    "exceedances by case, not confirmed failure causes."
)
