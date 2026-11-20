
from pathlib import Path
import sys
import html

import pandas as pd
import streamlit as st

# --------------------------------------------------
# PATHS AND DATABASE
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from modules import maintenance_db

# --------------------------------------------------
# PAGE STYLING
# --------------------------------------------------

st.html("""
<style>

/* Main page */

.main-header {
    font-size: 30px;
    font-weight: 750;
    color: #172B43;
    margin-bottom: 4px;
}

.section-heading {
    font-size: 21px;
    font-weight: 700;
    color: #172B43;
    margin-bottom: 4px;
}

.section-description {
    font-size: 13px;
    color: #64748B;
    margin-bottom: 16px;
}

/* KPI cards */

.kpi-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 14px;
    margin: 12px 0 10px 0;
}

.kpi-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 17px 18px;
    position: relative;
    overflow: hidden;
    min-height: 112px;
    box-shadow: 0 2px 7px rgba(15, 23, 42, 0.035);
}

.kpi-card::before {
    content: "";
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 5px;
    background: var(--accent);
}

.kpi-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
}

.kpi-label {
    font-size: 12px;
    font-weight: 650;
    color: #64748B;
}

.kpi-icon {
    font-size: 19px;
}

.kpi-value {
    font-size: 28px;
    font-weight: 750;
    color: #172B43;
    line-height: 1.2;
}

/* Information banners */

.info-banner {
    background: #EFF6FF;
    border: 1px solid #BFDBFE;
    border-radius: 9px;
    padding: 12px 15px;
    color: #1E40AF;
    font-size: 13px;
    margin: 12px 0;
}

.warning-banner {
    background: #FFFBEB;
    border: 1px solid #FDE68A;
    border-radius: 9px;
    padding: 12px 15px;
    color: #92400E;
    font-size: 13px;
    margin: 12px 0;
}

/* Alert table */

.alert-table-wrapper {
    width: 100%;
    overflow-x: auto;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    margin-top: 12px;
}

.alert-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
    white-space: nowrap;
}

.alert-table th {
    background: #F1F5F9;
    color: #475569;
    font-weight: 700;
    text-align: left;
    padding: 13px 12px;
    border-bottom: 1px solid #E2E8F0;
}

.alert-table td {
    padding: 12px;
    color: #334155;
    border-bottom: 1px solid #EDF1F5;
}

.alert-table tr:last-child td {
    border-bottom: none;
}

.alert-table tbody tr:hover {
    background: #F8FAFC;
}

.severity-pill,
.status-pill {
    display: inline-block;
    padding: 4px 9px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
}

.severity-critical {
    color: #B91C1C;
    background: #FEE2E2;
}

.severity-warning {
    color: #92400E;
    background: #FEF3C7;
}

.status-open {
    color: #1D4ED8;
    background: #DBEAFE;
}

.status-acknowledged {
    color: #6D28D9;
    background: #EDE9FE;
}

.status-resolved {
    color: #047857;
    background: #D1FAE5;
}

.alert-id {
    font-weight: 700;
    color: #1D4ED8;
}

.timestamp {
    color: #64748B;
    font-size: 11px;
}

/* Supporting text */

.status-summary {
    font-size: 13px;
    color: #64748B;
    margin: 10px 0 16px 0;
}

.muted-note {
    font-size: 12px;
    color: #64748B;
    margin-top: 9px;
}

/* Primary buttons - matching Work Orders page */

div.stButton > button[kind="primary"] {
    background-color: #2563EB !important;
    color: #FFFFFF !important;
    border: 1px solid #2563EB !important;
    border-radius: 8px !important;
    font-weight: 650 !important;
    min-height: 40px;
    padding: 7px 18px !important;
    white-space: nowrap;
}

div.stButton > button[kind="primary"] *,
div.stButton > button[kind="primary"] span,
div.stButton > button[kind="primary"] p {
    color: #FFFFFF !important;
}

div.stButton > button[kind="primary"]:hover {
    background-color: #1D4ED8 !important;
    border-color: #1D4ED8 !important;
    color: #FFFFFF !important;
}

div.stButton > button[kind="primary"]:disabled {
    background-color: #E2E8F0 !important;
    border-color: #E2E8F0 !important;
    color: #94A3B8 !important;
    opacity: 1 !important;
}

div.stButton > button[kind="primary"]:disabled * {
    color: #94A3B8 !important;
}

/* Input controls */

div[data-testid="stNumberInput"] input,
div[data-testid="stSelectbox"] div[data-baseweb="select"] {
    border-radius: 7px;
}

div[data-testid="stNumberInput"] button {
    color: #334155 !important;
}

/* Footer */

.footer-note {
    font-size: 12px;
    color: #94A3B8;
    text-align: center;
    padding: 8px 0 4px 0;
}

@media (max-width: 800px) {
    .kpi-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

</style>
""")

# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------

def safe_text(value):
    if pd.isna(value):
        return "—"
    return html.escape(str(value))


def format_timestamp(value):
    if pd.isna(value):
        return "—"

    try:
        timestamp = pd.to_datetime(value)
        return timestamp.strftime("%b %d, %Y · %H:%M:%S")
    except (ValueError, TypeError):
        return safe_text(value)


def severity_badge(severity):
    severity_text = str(severity).strip()

    if severity_text.lower() == "critical":
        css_class = "severity-critical"
    else:
        css_class = "severity-warning"

    return (
        f'<span class="severity-pill {css_class}">'
        f'{safe_text(severity_text)}</span>'
    )


def status_badge(status):
    status_text = str(status).strip()

    status_classes = {
        "open": "status-open",
        "acknowledged": "status-acknowledged",
        "resolved": "status-resolved"
    }

    css_class = status_classes.get(
        status_text.lower(),
        "status-open"
    )

    return (
        f'<span class="status-pill {css_class}">'
        f'{safe_text(status_text)}</span>'
    )


def render_kpi_cards(cards):
    card_html = '<div class="kpi-grid">'

    for label, value, icon, accent in cards:
        card_html += f"""
        <div class="kpi-card" style="--accent:{accent};">
            <div class="kpi-top">
                <span class="kpi-label">{label}</span>
                <span class="kpi-icon">{icon}</span>
            </div>
            <div class="kpi-value">{value}</div>
        </div>
        """

    card_html += "</div>"

    st.html(card_html)


def render_alert_table(dataframe):
    if dataframe.empty:
        st.info("No alerts match the selected filters.")
        return

    rows = ""

    for _, alert in dataframe.iterrows():

        rows += f"""
        <tr>
            <td>
                <span class="alert-id">
                    #{safe_text(alert['id'])}
                </span>
            </td>
            <td>{safe_text(alert['experiment'])}</td>
            <td>{safe_text(alert['case_id'])}</td>
            <td>{safe_text(alert['run_id'])}</td>
            <td><strong>{float(alert['wear_value']):.4f}</strong></td>
            <td>{severity_badge(alert['severity'])}</td>
            <td>{status_badge(alert['status'])}</td>
            <td>
                <span class="timestamp">
                    {format_timestamp(alert['created_at'])}
                </span>
            </td>
        </tr>
        """

    table_html = f"""
    <div class="alert-table-wrapper">
        <table class="alert-table">
            <thead>
                <tr>
                    <th>Alert ID</th>
                    <th>Experiment</th>
                    <th>Case</th>
                    <th>Run</th>
                    <th>Measured VB</th>
                    <th>Severity</th>
                    <th>Status</th>
                    <th>Created At</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
    </div>
    """

    st.html(table_html)


# --------------------------------------------------
# HEADER
# --------------------------------------------------

st.html("""
<div class="main-header">Alert Centre</div>
<div class="section-description">
    Monitor measured tool-wear alerts and manage maintenance alert status.
</div>
""")

maintenance_db.initialise_database()

st.divider()

# --------------------------------------------------
# ALERT THRESHOLD SETTINGS
# --------------------------------------------------

st.html("""
<div class="section-heading">Alert Threshold Settings</div>
<div class="section-description">
    Configure the prototype thresholds used to classify measured tool wear.
</div>
""")

with st.container(border=True):

    threshold_col1, threshold_col2 = st.columns(2, gap="large")

    with threshold_col1:

        st.markdown(
            '<span style="color:#D97706;">●</span> '
            '**Warning threshold (VB)**',
            unsafe_allow_html=True
        )

        warning_threshold = st.number_input(
            "Warning threshold (VB)",
            min_value=0.01,
            max_value=1.53,
            value=0.50,
            step=0.05,
            format="%.2f",
            label_visibility="collapsed"
        )

    with threshold_col2:

        st.markdown(
            '<span style="color:#DC2626;">●</span> '
            '**Critical threshold (VB)**',
            unsafe_allow_html=True
        )

        critical_threshold = st.number_input(
            "Critical threshold (VB)",
            min_value=0.01,
            max_value=1.53,
            value=0.80,
            step=0.05,
            format="%.2f",
            label_visibility="collapsed"
        )

    if critical_threshold <= warning_threshold:

        st.error(
            "Critical threshold must be higher than "
            "the warning threshold."
        )

        st.stop()

    st.html(f"""
    <div class="info-banner">
        <strong>Current thresholds:</strong>
        <span style="color:#D97706; font-weight:700;">
            Warning: VB ≥ {warning_threshold:.2f}
        </span>
        &nbsp; | &nbsp;
        <span style="color:#DC2626; font-weight:700;">
            Critical: VB ≥ {critical_threshold:.2f}
        </span>
    </div>
    """)

    st.caption(
        "These are configurable prototype thresholds, "
        "not validated industrial failure limits."
    )

st.divider()

# --------------------------------------------------
# GET CURRENT ALERTS
# --------------------------------------------------

alerts = maintenance_db.get_alerts()

# --------------------------------------------------
# ALERT ACTIONS
# --------------------------------------------------

st.html("""
<div class="section-heading">Alert Actions</div>
<div class="section-description">
    Generate missing alerts and update the status of existing alerts.
</div>
""")

generate_col, manage_col = st.columns([1, 1], gap="large")

# --------------------------------------------------
# GENERATE MAINTENANCE ALERTS
# --------------------------------------------------

with generate_col:

    with st.container(border=True):

        st.markdown("#### Generate Maintenance Alerts")

        st.write(
            "Check the dataset and generate any missing "
            "measured tool-wear alerts."
        )

        st.html("""
        <div class="warning-banner">
            Alert generation uses measured VB values,
            not AI-predicted values.
        </div>
        """)

        if st.button(
            "Generate Missing Alerts",
            type="primary",
            key="generate_alerts"
        ):

            from scipy.io import loadmat
            import numpy as np

            data_path = (
                BASE_DIR
                / "Data_Milling_Machine"
                / "mill.mat"
            )

            if not data_path.exists():

                st.error("NASA dataset not found.")

            else:

                try:

                    experiments = loadmat(
                        str(data_path)
                    )["mill"]

                    existing_alerts = maintenance_db.get_alerts()

                    existing_experiments = {
                        (
                            int(alert["experiment"]),
                            alert["value_source"]
                        )
                        for alert in existing_alerts
                    }

                    generated_count = 0
                    skipped_count = 0

                    for i in range(experiments.shape[1]):

                        record = experiments[0, i]

                        wear = float(
                            np.asarray(record["VB"]).squeeze()
                        )

                        if not np.isfinite(wear):
                            skipped_count += 1
                            continue

                        if wear < warning_threshold:
                            continue

                        experiment = i + 1
                        source = "Measured"

                        if (experiment, source) in existing_experiments:
                            continue

                        case_id = int(
                            np.asarray(record["case"]).squeeze()
                        )

                        run_id = int(
                            np.asarray(record["run"]).squeeze()
                        )

                        if wear >= critical_threshold:

                            severity = "Critical"

                            message = (
                                "Measured tool wear has reached "
                                "the critical prototype threshold."
                            )

                        else:

                            severity = "Warning"

                            message = (
                                "Measured tool wear has reached "
                                "the warning prototype threshold."
                            )

                        maintenance_db.add_alert(
                            experiment=experiment,
                            case_id=case_id,
                            run_id=run_id,
                            wear_value=wear,
                            value_source=source,
                            severity=severity,
                            message=message
                        )

                        existing_experiments.add(
                            (experiment, source)
                        )

                        generated_count += 1

                    if generated_count:
                        st.success(
                            f"{generated_count} new alert(s) generated."
                        )
                    else:
                        st.info(
                            "No new alerts were required. "
                            "Existing alerts are already up to date."
                        )

                    if skipped_count:
                        st.caption(
                            f"{skipped_count} experiment(s) with "
                            "invalid or missing wear values skipped."
                        )

                    st.rerun()

                except Exception as error:

                    st.error(
                        f"Could not generate alerts: {error}"
                    )

# --------------------------------------------------
# MANAGE ALERT STATUS
# --------------------------------------------------

with manage_col:

    with st.container(border=True):

        st.markdown("#### Manage Alert Status")

        st.write(
            "Select an existing alert and update its maintenance status."
        )

        if alerts:

            alert_options = {
                (
                    f"Alert #{a['id']} | "
                    f"Experiment {a['experiment']} | "
                    f"{a['severity']} | {a['status']}"
                ): a["id"]
                for a in alerts
            }

            selected_label = st.selectbox(
                "Select alert",
                list(alert_options.keys()),
                key="manage_alert_selection"
            )

            selected_alert_id = alert_options[selected_label]

            selected_alert = next(
                a for a in alerts
                if a["id"] == selected_alert_id
            )

            valid_statuses = [
                "Open",
                "Acknowledged",
                "Resolved"
            ]

            current_status = selected_alert["status"]

            new_status = st.selectbox(
                "New status",
                valid_statuses,
                index=(
                    valid_statuses.index(current_status)
                    if current_status in valid_statuses
                    else 0
                ),
                key="manage_alert_new_status"
            )

            status_changed = (
                new_status != current_status
            )

            if st.button(
                "Update Alert Status",
                type="primary",
                key="update_alert_status",
                disabled=not status_changed
            ):

                maintenance_db.update_alert_status(
                    selected_alert_id,
                    new_status
                )

                st.success("Alert status updated.")
                st.rerun()

        else:

            st.info(
                "No alerts available. Generate alerts first."
            )

# --------------------------------------------------
# ALERT HISTORY
# --------------------------------------------------

st.divider()

st.html("""
<div class="section-heading">Alert History</div>
<div class="section-description">
    Review, filter and monitor all recorded maintenance alerts.
</div>
""")

alerts = maintenance_db.get_alerts()

if alerts:

    alert_df = pd.DataFrame(alerts)

    # ----------------------------------------------
    # KPI CALCULATIONS
    # ----------------------------------------------

    total_alerts = len(alert_df)

    critical_count = (
        alert_df["severity"] == "Critical"
    ).sum()

    warning_count = (
        alert_df["severity"] == "Warning"
    ).sum()

    open_count = (
        alert_df["status"] == "Open"
    ).sum()

    acknowledged_count = (
        alert_df["status"] == "Acknowledged"
    ).sum()

    resolved_count = (
        alert_df["status"] == "Resolved"
    ).sum()

    render_kpi_cards([
        ("Total Alerts", total_alerts, "📋", "#2563EB"),
        ("Critical Alerts", int(critical_count), "🚨", "#DC2626"),
        ("Warnings", int(warning_count), "⚠️", "#D97706"),
        ("Open Alerts", int(open_count), "🔔", "#0D9488")
    ])

    st.markdown(
        f"""
        <div class="status-summary">
            Acknowledged: <strong>{acknowledged_count}</strong>
            &nbsp; | &nbsp;
            Resolved: <strong>{resolved_count}</strong>
        </div>
        """,
        unsafe_allow_html=True
    )

    # ----------------------------------------------
    # FILTERS AND UNIFIED ALERT TABLE
    # ----------------------------------------------

    with st.container(border=True):

        st.markdown("#### Filter Alerts")

        filter_col1, filter_col2 = st.columns(2, gap="large")

        with filter_col1:
            severity_filter = st.selectbox(
                "Severity",
                ["All", "Critical", "Warning"],
                key="alert_severity_filter"
            )

        with filter_col2:
            status_filter = st.selectbox(
                "Status",
                ["All", "Open", "Acknowledged", "Resolved"],
                key="alert_status_filter"
            )

        filtered_alerts = alert_df.copy()

        if severity_filter != "All":
            filtered_alerts = filtered_alerts[
                filtered_alerts["severity"] == severity_filter
            ]

        if status_filter != "All":
            filtered_alerts = filtered_alerts[
                filtered_alerts["status"] == status_filter
            ]

        st.caption(
            f"Showing {len(filtered_alerts)} of {total_alerts} alerts."
        )

        render_alert_table(filtered_alerts)

else:

    with st.container(border=True):
        st.info(
            "No alerts available. Generate alerts to populate "
            "the Alert Centre."
        )

# --------------------------------------------------
# FOOTER
# --------------------------------------------------

st.divider()

st.html("""
<div class="footer-note">
    Alert records are stored in the independent
    milling machine SQLite database.
</div>
""")
