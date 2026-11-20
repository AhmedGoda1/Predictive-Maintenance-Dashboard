import streamlit as st
import pandas as pd
from pathlib import Path
import sys
import html

# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------

st.set_page_config(
    page_title="Overview | Milling Monitor",
    page_icon="⚙️",
    layout="wide"
)

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from modules import maintenance_db


# --------------------------------------------------
# FILE PATHS
# --------------------------------------------------

DATA_PATH = BASE_DIR / "database" / "milling_features.csv"
MODEL_PATH = BASE_DIR / "models" / "milling_wear_model.joblib"
IMAGE_PATH = BASE_DIR / "assets" / "milling_machine.jpg"


# --------------------------------------------------
# CUSTOM STYLE
# --------------------------------------------------

st.markdown("""
<style>

.stApp {
    background-color: #F3F6FA;
}

.block-container {
    padding-top: 2rem;
    padding-bottom: 1.2rem;
    max-width: 1450px;
}

/* Dedicated spacing around the Overview header */
.st-key-overview-header {
    padding-top: 16px;
    padding-bottom: 12px;
}

/* Keep the thumbnail compact and vertically aligned */
.st-key-overview-header [data-testid="stImage"] img {
    width: 68px !important;
    height: 58px !important;
    object-fit: cover !important;
    border-radius: 11px !important;
    border: 2px solid #E2E8F0;
    box-shadow: 0 3px 9px rgba(23,43,67,0.10);
}


/* HEADER */

.main-header {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 30px;
    font-weight: 750;
    color: #172B43;
    letter-spacing: -0.6px;
    margin-bottom: 3px;
}

.header-image {
    width: 68px;
    height: 58px;
    object-fit: cover;
    border-radius: 11px;
    border: 2px solid #E2E8F0;
    box-shadow: 0 3px 9px rgba(23,43,67,0.10);
}

.sub-header {
    font-size: 13px;
    color: #718096;
    margin-bottom: 13px;
}


/* SECTION HEADINGS */

.section-title {
    color: #172B43;
    font-size: 19px;
    font-weight: 750;
    margin-top: 15px;
    margin-bottom: 11px;
    letter-spacing: -0.2px;
}

.section-description {
    color: #718096;
    font-size: 12px;
    margin-top: -7px;
    margin-bottom: 10px;
}


/* KPI CARDS */

.metric-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-left: 4px solid #64748B;
    border-radius: 12px;
    padding: 14px 16px;
    min-height: 112px;
    box-shadow: 0 3px 10px rgba(23,43,67,0.04);
}

.metric-blue {
    border-left-color: #3478C5;
}

.metric-purple {
    border-left-color: #8064B5;
}

.metric-amber {
    border-left-color: #D99A27;
}

.metric-green {
    border-left-color: #29966A;
}

.metric-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 5px;
}

.metric-label {
    color: #64748B;
    font-size: 11px;
    font-weight: 750;
    text-transform: uppercase;
    letter-spacing: 0.35px;
}

.metric-icon {
    font-size: 18px;
}

.metric-value {
    color: #172B43;
    font-size: 29px;
    font-weight: 750;
    margin-top: 9px;
    line-height: 1.1;
}

.metric-note {
    color: #94A3B8;
    font-size: 11px;
    margin-top: 5px;
}


/* SYSTEM STATUS */

.status-chip {
    display: flex;
    align-items: center;
    gap: 9px;
    background: #EAF7EF;
    border: 1px solid #D2EBDD;
    border-radius: 9px;
    padding: 10px 13px;
    min-height: 42px;
    color: #276749;
    font-size: 12px;
    font-weight: 650;
}

.status-dot {
    width: 9px;
    height: 9px;
    min-width: 9px;
    border-radius: 50%;
    background: #22A06B;
}

.status-chip.warning {
    background: #FFF7E8;
    border-color: #F4E2B8;
    color: #9A6700;
}

.status-chip.warning .status-dot {
    background: #D99A27;
}

.status-chip.error {
    background: #FEF0F0;
    border-color: #F5D0D0;
    color: #B42318;
}

.status-chip.error .status-dot {
    background: #DC4545;
}


/* TABLE */

.overview-table-wrapper {
    width: 100%;
    overflow-x: auto;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    background: #FFFFFF;
}

.overview-table {
    width: 100%;
    min-width: 780px;
    border-collapse: collapse;
    font-size: 12px;
    color: #334155;
}

.overview-table th {
    background: #F5F8FC;
    color: #52657B;
    font-size: 10px;
    font-weight: 750;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    text-align: left;
    padding: 11px 12px;
    border-bottom: 1px solid #E2E8F0;
    white-space: nowrap;
}

.overview-table td {
    padding: 11px 12px;
    border-bottom: 1px solid #EDF1F5;
    vertical-align: middle;
}

.overview-table tbody tr:last-child td {
    border-bottom: none;
}

.overview-table tbody tr:hover td {
    background: #F8FAFD;
}

.table-id {
    color: #64748B;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
}

.table-number {
    text-align: right;
    font-variant-numeric: tabular-nums;
}

.table-wear {
    font-weight: 700;
    color: #475569;
    text-align: right;
    font-variant-numeric: tabular-nums;
}

.table-wear-high {
    color: #B45309;
    font-weight: 750;
    background: #FFF7E8;
    border-radius: 6px;
    padding: 4px 7px;
    display: inline-block;
}

.table-task {
    color: #203B5A;
    font-weight: 650;
    min-width: 170px;
}

.table-muted {
    color: #94A3B8;
}

.table-timestamp {
    color: #718096;
    font-family: Consolas, monospace;
    font-size: 11px;
    white-space: nowrap;
}


/* BADGES */

.pill {
    display: inline-block;
    padding: 4px 9px;
    border-radius: 20px;
    font-size: 10px;
    font-weight: 750;
    white-space: nowrap;
}

.pill-warning {
    background: #FFF4DE;
    color: #A16207;
}

.pill-critical {
    background: #FEE2E2;
    color: #B91C1C;
}

.pill-open {
    background: #FFF4DE;
    color: #A16207;
}

.pill-progress {
    background: #E8F1FF;
    color: #245EA8;
}

.pill-completed {
    background: #DCFCE7;
    color: #15803D;
}

.pill-cancelled {
    background: #F1F5F9;
    color: #64748B;
}

.pill-low {
    background: #E8F5EE;
    color: #27734B;
}

.pill-medium {
    background: #E8F1FF;
    color: #245EA8;
}

.pill-high {
    background: #FFF4DE;
    color: #A16207;
}


/* SIDEBAR */

section[data-testid="stSidebar"] {
    background-color: #172B43;
}

section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
    color: #F8FAFC !important;
}

section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] strong {
    color: #F8FAFC !important;
}


/* FOOTER */

.page-footer {
    border-top: 1px solid #E2E8F0;
    padding-top: 10px;
    margin-top: 14px;
    color: #94A3B8;
    font-size: 11px;
}

</style>
""", unsafe_allow_html=True)


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------

def safe_text(value):

    if value is None or pd.isna(value):
        return ""

    return html.escape(str(value))


def format_timestamp(value):

    if value is None or pd.isna(value):
        return "—"

    try:
        parsed = pd.to_datetime(value)
        return parsed.strftime("%b %d, %Y · %H:%M:%S")

    except (ValueError, TypeError):
        return str(value)


def severity_badge(severity):

    severity = str(severity).strip()

    if severity.lower() == "critical":
        css_class = "pill-critical"

    elif severity.lower() == "warning":
        css_class = "pill-warning"

    else:
        css_class = "pill-warning"

    return (
        f'<span class="pill {css_class}">'
        f'{safe_text(severity)}</span>'
    )


def status_badge(status):

    classes = {
        "Open": "pill-open",
        "In Progress": "pill-progress",
        "Completed": "pill-completed",
        "Cancelled": "pill-cancelled"
    }

    css_class = classes.get(status, "pill-cancelled")

    return (
        f'<span class="pill {css_class}">'
        f'{safe_text(status)}</span>'
    )


def priority_badge(priority):

    classes = {
        "Low": "pill-low",
        "Medium": "pill-medium",
        "High": "pill-high",
        "Critical": "pill-critical"
    }

    css_class = classes.get(priority, "pill-low")

    return (
        f'<span class="pill {css_class}">'
        f'{safe_text(priority)}</span>'
    )


def wear_display(value):

    try:

        number = float(value)

        if not pd.notna(number):
            return "—"

        formatted = f"{number:.3f}"

        if number >= 0.8:

            return (
                '<span class="table-wear-high">'
                f'{formatted}</span>'
            )

        return (
            f'<span class="table-wear">{formatted}</span>'
        )

    except (ValueError, TypeError):

        return "—"


def status_chip(label, state):

    if state == "available":

        return f"""
        <div class="status-chip">
            <span class="status-dot"></span>
            <span>✓ {safe_text(label)}</span>
        </div>
        """

    elif state == "warning":

        return f"""
        <div class="status-chip warning">
            <span class="status-dot"></span>
            <span>! {safe_text(label)}</span>
        </div>
        """

    else:

        return f"""
        <div class="status-chip error">
            <span class="status-dot"></span>
            <span>✕ {safe_text(label)}</span>
        </div>
        """


# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------

maintenance_db.initialise_database()

alerts = maintenance_db.get_alerts()
work_orders = maintenance_db.get_work_orders()

if DATA_PATH.exists():
    features = pd.read_csv(DATA_PATH)
else:
    features = pd.DataFrame()


# --------------------------------------------------
# HEADER WITH REAL CNC MACHINE IMAGE
# --------------------------------------------------

with st.container(key="overview-header"):

    header_col1, header_col2 = st.columns(
        [0.85, 10],
        vertical_alignment="center",
        gap="small"
    )

    with header_col1:

        if IMAGE_PATH.exists():
            st.image(
                str(IMAGE_PATH),
                width=68
            )
        else:
            st.warning("Machine image not found")

    with header_col2:

        st.html("""
        <div class="main-header">
            Milling Machine Monitor
        </div>
        """)

    st.html("""
    <div class="sub-header">
        Industrial monitoring | AI-based tool wear estimation |
        Maintenance management
    </div>
    """)

st.divider()


# --------------------------------------------------
# KPI CALCULATIONS
# --------------------------------------------------

total_experiments = len(features)

if "VB" in features.columns:
    average_wear = features["VB"].dropna().mean()
else:
    average_wear = float("nan")

open_alerts = sum(
    1 for alert in alerts
    if alert.get("status") == "Open"
)

open_work_orders = sum(
    1 for order in work_orders
    if order.get("status") in ["Open", "In Progress"]
)


# --------------------------------------------------
# MACHINE OVERVIEW KPI CARDS
# --------------------------------------------------

st.html("""
<div class="section-title">Machine Overview</div>
""")

kpi_columns = st.columns(4)

kpi_data = [
    {
        "label": "Experiments Available",
        "value": str(total_experiments),
        "note": "NASA milling dataset",
        "icon": "📊",
        "colour": "metric-blue"
    },
    {
        "label": "Average Measured Wear (VB)",
        "value": (
            f"{average_wear:.3f}"
            if pd.notna(average_wear)
            else "N/A"
        ),
        "note": "Mean of available measurements",
        "icon": "📈",
        "colour": "metric-purple"
    },
    {
        "label": "Open Alerts",
        "value": str(open_alerts),
        "note": "Awaiting resolution",
        "icon": "⚠️",
        "colour": "metric-amber"
    },
    {
        "label": "Active Work Orders",
        "value": str(open_work_orders),
        "note": "Open or in progress",
        "icon": "🔧",
        "colour": "metric-green"
    }
]

for column, item in zip(kpi_columns, kpi_data):

    with column:

        st.html(
            f"""
            <div class="metric-card {item['colour']}">
                <div class="metric-top">
                    <div class="metric-label">
                        {item['label']}
                    </div>
                    <div class="metric-icon">
                        {item['icon']}
                    </div>
                </div>

                <div class="metric-value">
                    {item['value']}
                </div>

                <div class="metric-note">
                    {item['note']}
                </div>
            </div>
            """
        )


# --------------------------------------------------
# SYSTEM STATUS
# --------------------------------------------------

st.html("""
<div class="section-title">System Status</div>
""")

status1, status2, status3 = st.columns(3)

with status1:

    dataset_state = (
        "available"
        if not features.empty
        else "error"
    )

    st.html(
        status_chip(
            "Dataset available"
            if dataset_state == "available"
            else "Dataset not found",
            dataset_state
        )
    )

with status2:

    model_state = (
        "available"
        if MODEL_PATH.exists()
        else "warning"
    )

    st.html(
        status_chip(
            "AI model available"
            if model_state == "available"
            else "AI model not found",
            model_state
        )
    )

with status3:

    st.html(
        status_chip(
            "Maintenance database ready",
            "available"
        )
    )


# --------------------------------------------------
# RECENT MAINTENANCE ALERTS
# --------------------------------------------------

st.html("""
<div class="section-title">Recent Maintenance Alerts</div>
<div class="section-description">
    Latest recorded alerts from the maintenance database.
</div>
""")

if alerts:

    alert_df = pd.DataFrame(alerts)

    recent_alerts = alert_df.head(5)

    table_rows = []

    for _, record in recent_alerts.iterrows():

        table_rows.append(
            "<tr>"
            f'<td class="table-id">#{safe_text(record.get("id"))}</td>'
            f'<td>{safe_text(record.get("experiment"))}</td>'
            f'<td>{safe_text(record.get("case_id"))}</td>'
            f'<td class="table-number">'
            f'{wear_display(record.get("wear_value"))}'
            '</td>'
            f'<td>{severity_badge(record.get("severity"))}</td>'
            f'<td>{status_badge(record.get("status"))}</td>'
            f'<td class="table-timestamp">'
            f'{safe_text(format_timestamp(record.get("created_at")))}'
            '</td>'
            "</tr>"
        )

    alert_table = (
        '<div class="overview-table-wrapper">'
        '<table class="overview-table">'
        '<thead><tr>'
        '<th>ID</th>'
        '<th>Experiment</th>'
        '<th>Case ID</th>'
        '<th style="text-align:right;">Wear Value</th>'
        '<th>Severity</th>'
        '<th>Status</th>'
        '<th>Created At</th>'
        '</tr></thead>'
        '<tbody>'
        + "".join(table_rows)
        + '</tbody></table></div>'
    )

    st.html(alert_table)

else:

    st.info("No maintenance alerts have been generated yet.")


# --------------------------------------------------
# RECENT WORK ORDERS
# --------------------------------------------------

st.html("""
<div class="section-title">Recent Work Orders</div>
<div class="section-description">
    Latest maintenance activities and assigned technicians.
</div>
""")

if work_orders:

    work_df = pd.DataFrame(work_orders)

    recent_work_orders = work_df.head(5)

    work_rows = []

    for _, record in recent_work_orders.iterrows():

        assigned_to = record.get("assigned_to")

        if (
            assigned_to is None
            or pd.isna(assigned_to)
            or not str(assigned_to).strip()
        ):

            assigned_html = (
                '<span class="table-muted">Unassigned</span>'
            )

        else:

            assigned_html = safe_text(assigned_to)

        work_rows.append(
            "<tr>"
            f'<td class="table-id">#{safe_text(record.get("id"))}</td>'
            f'<td class="table-id">{safe_text(record.get("alert_id"))}</td>'
            f'<td class="table-task">{safe_text(record.get("task"))}</td>'
            f'<td>{assigned_html}</td>'
            f'<td>{priority_badge(record.get("priority"))}</td>'
            f'<td>{status_badge(record.get("status"))}</td>'
            "</tr>"
        )

    work_table = (
        '<div class="overview-table-wrapper">'
        '<table class="overview-table">'
        '<thead><tr>'
        '<th>ID</th>'
        '<th>Alert ID</th>'
        '<th>Task</th>'
        '<th>Assigned To</th>'
        '<th>Priority</th>'
        '<th>Status</th>'
        '</tr></thead>'
        '<tbody>'
        + "".join(work_rows)
        + '</tbody></table></div>'
    )

    st.html(work_table)

else:

    st.info(
        "No maintenance work orders have been created yet."
    )


# --------------------------------------------------
# FOOTER
# --------------------------------------------------

st.html("""
<div class="page-footer">
    Prototype monitoring dashboard using the NASA milling
    machine dataset. Tool-wear values and alert thresholds are
    experimental and should not be interpreted as validated
    industrial safety limits.
</div>
""")