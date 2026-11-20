
from pathlib import Path
import sys
import html

import pandas as pd
import streamlit as st

# --------------------------------------------------
# DATABASE CONNECTION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from modules import maintenance_db

maintenance_db.initialise_database()


# --------------------------------------------------
# VISUAL STYLING
# --------------------------------------------------

st.markdown("""
<style>

/* PAGE */

.main-title {
    font-size: 30px;
    font-weight: 750;
    color: #172B43;
    letter-spacing: -0.7px;
    margin-bottom: 3px;
}

.page-subtitle {
    color: #718096;
    font-size: 14px;
    margin-bottom: 23px;
}

.panel-title {
    color: #203B5A;
    font-size: 19px;
    font-weight: 750;
    margin-bottom: 5px;
}

.section-description {
    color: #718096;
    font-size: 13px;
    margin-bottom: 17px;
}


/* KPI CARDS */

.kpi-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-left: 4px solid #64748B;
    border-radius: 12px;
    padding: 17px 18px;
    min-height: 108px;
    box-shadow: 0 3px 10px rgba(23,43,67,0.04);
}

.kpi-blue { border-left-color: #3478C5; }
.kpi-amber { border-left-color: #D99A27; }
.kpi-purple { border-left-color: #8064B5; }
.kpi-green { border-left-color: #29966A; }

.kpi-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.kpi-label {
    color: #718096;
    font-size: 11px;
    font-weight: 750;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.kpi-icon { font-size: 19px; }

.kpi-value {
    color: #172B43;
    font-size: 30px;
    font-weight: 750;
    margin-top: 8px;
    line-height: 1.15;
}

.kpi-note {
    color: #94A3B8;
    font-size: 12px;
    margin-top: 5px;
}


/* OUTER CARDS */

div[data-testid="stVerticalBlockBorderWrapper"] {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 14px;
    box-shadow: 0 3px 12px rgba(23,43,67,0.045);
}


/* REMOVE NESTED FORM BORDER */

div[data-testid="stForm"] {
    border: none !important;
    padding: 0 !important;
}


/* INPUT LABELS */

div[data-testid="stSelectbox"] label,
div[data-testid="stTextInput"] label,
div[data-testid="stTextArea"] label {
    color: #334155;
    font-size: 13px;
    font-weight: 650;
}


/* INPUT APPEARANCE */

div[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea {
    border-radius: 9px;
    border-color: #CBD5E1;
    background: #FFFFFF;
}

div[data-testid="stSelectbox"] div[data-baseweb="select"] > div:hover,
div[data-testid="stTextInput"] input:hover,
div[data-testid="stTextArea"] textarea:hover {
    border-color: #7CA5D5;
}


/* PRIMARY BUTTONS - COMMON STYLE */

div[data-testid="stFormSubmitButton"] button,
div[data-testid="stButton"] button[kind="primary"] {
    background-color: #2563EB !important;
    color: #FFFFFF !important;
    border: 1px solid #2563EB !important;
    border-radius: 9px !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    min-height: 40px !important;
    padding: 8px 16px !important;
    white-space: nowrap !important;
    transition: background-color 0.2s ease, box-shadow 0.2s ease;
}


/* FORCE BUTTON TEXT AND ICONS TO WHITE */

div[data-testid="stFormSubmitButton"] button *,
div[data-testid="stButton"] button[kind="primary"] * {
    color: #FFFFFF !important;
    fill: #FFFFFF !important;
    font-weight: 600 !important;
    white-space: nowrap !important;
}


/* CREATE BUTTON WIDTH */

div[data-testid="stFormSubmitButton"] button {
    min-width: 175px !important;
}


/* UPDATE BUTTON WIDTH */

div[data-testid="stButton"] button[kind="primary"] {
    min-width: 140px !important;
}


/* BUTTON HOVER */

div[data-testid="stFormSubmitButton"] button:hover,
div[data-testid="stButton"] button[kind="primary"]:hover {
    background-color: #1D4ED8 !important;
    border-color: #1D4ED8 !important;
    color: #FFFFFF !important;
    cursor: pointer;
    box-shadow: 0 3px 8px rgba(37,99,235,0.20);
}


/* DISABLED BUTTON */

div[data-testid="stButton"] button:disabled,
div[data-testid="stFormSubmitButton"] button:disabled {
    background-color: #E2E8F0 !important;
    border-color: #E2E8F0 !important;
    color: #94A3B8 !important;
    cursor: not-allowed;
    box-shadow: none;
}

div[data-testid="stButton"] button:disabled *,
div[data-testid="stFormSubmitButton"] button:disabled * {
    color: #94A3B8 !important;
}


/* TABLE */

.work-table-wrapper {
    width: 100%;
    overflow-x: auto;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    background: #FFFFFF;
}

.work-table {
    width: 100%;
    min-width: 850px;
    border-collapse: collapse;
    font-size: 13px;
    color: #334155;
}

.work-table th {
    background: #F5F8FC;
    color: #52657B;
    font-size: 11px;
    font-weight: 750;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    text-align: left;
    padding: 13px 11px;
    border-bottom: 1px solid #E2E8F0;
    white-space: nowrap;
}

.work-table td {
    padding: 13px 11px;
    border-bottom: 1px solid #EDF1F5;
    vertical-align: middle;
}

.work-table tbody tr:last-child td {
    border-bottom: none;
}

.work-table tbody tr:hover td {
    background: #F8FAFD;
}

.table-id {
    color: #64748B;
    font-weight: 700;
}

.table-task {
    color: #203B5A;
    font-weight: 650;
    min-width: 175px;
}

.table-muted { color: #94A3B8; }

.table-timestamp {
    color: #718096;
    font-family: Consolas, monospace;
    font-size: 11px;
    white-space: nowrap;
}


/* STATUS AND PRIORITY PILLS */

.pill {
    display: inline-block;
    padding: 5px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 750;
    white-space: nowrap;
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

.pill-critical {
    background: #FEE2E2;
    color: #B91C1C;
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

section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] {
    border-radius: 9px;
    transition: background-color 0.2s ease;
}

section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover {
    background-color: #294564;
}


/* FOOTER */

.page-footer {
    border-top: 1px solid #E2E8F0;
    padding-top: 14px;
    margin-top: 8px;
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


def status_pill(status):
    classes = {
        "Open": "pill-open",
        "In Progress": "pill-progress",
        "Completed": "pill-completed",
        "Cancelled": "pill-cancelled"
    }
    css_class = classes.get(status, "pill-cancelled")
    return f'<span class="pill {css_class}">{safe_text(status)}</span>'


def priority_pill(priority):
    classes = {
        "Low": "pill-low",
        "Medium": "pill-medium",
        "High": "pill-high",
        "Critical": "pill-critical"
    }
    css_class = classes.get(priority, "pill-low")
    return f'<span class="pill {css_class}">{safe_text(priority)}</span>'


def format_timestamp(value):
    if value is None or pd.isna(value):
        return "—"

    try:
        parsed = pd.to_datetime(value)
        return parsed.strftime("%b %d, %Y · %H:%M")
    except (ValueError, TypeError):
        return str(value)


# --------------------------------------------------
# HEADER
# --------------------------------------------------

st.markdown(
    '<div class="main-title">Work Order Management</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="page-subtitle">'
    'Maintenance operations / Work order tracking'
    '</div>',
    unsafe_allow_html=True
)


# --------------------------------------------------
# LOAD DATABASE
# --------------------------------------------------

alerts = maintenance_db.get_alerts()
work_orders = maintenance_db.get_work_orders()

alert_lookup = {
    alert["id"]: alert
    for alert in alerts
}

work_df = pd.DataFrame(work_orders)

if not work_df.empty:

    work_df["experiment"] = work_df["alert_id"].map(
        lambda alert_id: (
            alert_lookup.get(alert_id, {}).get("experiment")
            if alert_id is not None
            else None
        )
    )

    work_df["assigned_to"] = (
        work_df["assigned_to"]
        .fillna("")
        .replace("", "Unassigned")
    )


# --------------------------------------------------
# KPI CARDS
# --------------------------------------------------

total_orders = len(work_orders)

open_orders = sum(
    order["status"] == "Open"
    for order in work_orders
)

progress_orders = sum(
    order["status"] == "In Progress"
    for order in work_orders
)

completed_orders = sum(
    order["status"] == "Completed"
    for order in work_orders
)

kpis = [
    ("TOTAL WORK ORDERS", total_orders, "All recorded tasks", "📋", "kpi-blue"),
    ("OPEN WORK ORDERS", open_orders, "Awaiting action", "🟠", "kpi-amber"),
    ("IN PROGRESS", progress_orders, "Currently active", "⚙️", "kpi-purple"),
    ("COMPLETED", completed_orders, "Finished tasks", "✓", "kpi-green")
]

columns = st.columns(4)

for column, item in zip(columns, kpis):

    label, value, note, icon, colour = item

    with column:

        st.markdown(
            f"""
            <div class="kpi-card {colour}">
                <div class="kpi-top">
                    <div class="kpi-label">{label}</div>
                    <div class="kpi-icon">{icon}</div>
                </div>
                <div class="kpi-value">{value}</div>
                <div class="kpi-note">{note}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

st.write("")


# --------------------------------------------------
# WORK ORDER HISTORY
# --------------------------------------------------

with st.container(border=True):

    st.markdown(
        '<div class="panel-title">Work Order History</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="section-description">'
        'Review and filter recorded maintenance activities.'
        '</div>',
        unsafe_allow_html=True
    )

    if not work_df.empty:

        filter_col1, filter_col2 = st.columns(2)

        with filter_col1:

            priority_filter = st.selectbox(
                "Priority",
                ["All", "Low", "Medium", "High", "Critical"],
                key="work_priority_filter"
            )

        with filter_col2:

            status_filter = st.selectbox(
                "Status",
                ["All", "Open", "In Progress", "Completed", "Cancelled"],
                key="work_status_filter"
            )

        filtered_df = work_df.copy()

        if priority_filter != "All":
            filtered_df = filtered_df[
                filtered_df["priority"] == priority_filter
            ]

        if status_filter != "All":
            filtered_df = filtered_df[
                filtered_df["status"] == status_filter
            ]

        rows = []

        for _, record in filtered_df.iterrows():

            experiment = (
                record["experiment"]
                if pd.notna(record["experiment"])
                else "Unknown"
            )

            technician = (
                record["assigned_to"]
                if record["assigned_to"]
                else "Unassigned"
            )

            rows.append(
                "<tr>"
                f'<td class="table-id">#{safe_text(record["id"])}</td>'
                f'<td class="table-id">{safe_text(record["alert_id"])}</td>'
                f'<td>{safe_text(experiment)}</td>'
                f'<td class="table-task">{safe_text(record["task"])}</td>'
                f'<td class="table-muted">{safe_text(technician)}</td>'
                f'<td>{priority_pill(record["priority"])}</td>'
                f'<td>{status_pill(record["status"])}</td>'
                f'<td class="table-timestamp">'
                f'{safe_text(format_timestamp(record["created_at"]))}'
                '</td>'
                "</tr>"
            )

        if rows:

            table_html = (
                '<div class="work-table-wrapper">'
                '<table class="work-table">'
                '<thead><tr>'
                '<th>Work Order</th>'
                '<th>Alert ID</th>'
                '<th>Experiment</th>'
                '<th>Maintenance Task</th>'
                '<th>Assigned Technician</th>'
                '<th>Priority</th>'
                '<th>Status</th>'
                '<th>Created At</th>'
                '</tr></thead>'
                '<tbody>'
                + "".join(rows)
                + '</tbody></table></div>'
            )

            st.html(table_html)

        else:
            st.info("No work orders match the selected filters.")

        st.caption(
            f"Showing {len(filtered_df)} of {total_orders} work orders."
        )

    else:
        st.info("No work orders have been created yet.")


# --------------------------------------------------
# CREATE AND UPDATE - TWO COLUMN LAYOUT
# --------------------------------------------------

st.write("")

create_col, update_col = st.columns([1.25, 1], gap="large")


# --------------------------------------------------
# CREATE NEW WORK ORDER
# --------------------------------------------------

with create_col:

    with st.container(border=True):

        st.markdown(
            '<div class="panel-title">＋ Create New Work Order</div>',
            unsafe_allow_html=True
        )

        st.markdown(
            '<div class="section-description">'
            'Create a maintenance task linked to an existing alert.'
            '</div>',
            unsafe_allow_html=True
        )

        if not alerts:

            st.info(
                "No alerts available. Generate an alert in the "
                "Alert Centre before creating a work order."
            )

        else:

            alert_options = {
                (
                    f"Alert #{a['id']} | "
                    f"Experiment {a['experiment']} | "
                    f"{a['severity']} | "
                    f"VB {float(a['wear_value']):.3f}"
                ): a
                for a in alerts
            }

            with st.form("modern_create_work_order", border=False):

                selected_alert_label = st.selectbox(
                    "Related maintenance alert",
                    list(alert_options.keys())
                )

                task = st.text_input(
                    "Maintenance task",
                    placeholder="Inspect milling cutting tool"
                )

                assigned_to = st.text_input(
                    "Assigned technician",
                    placeholder="Enter technician name"
                )

                priority = st.selectbox(
                    "Priority",
                    ["Low", "Medium", "High", "Critical"]
                )

                notes = st.text_area(
                    "Maintenance notes",
                    placeholder="Optional maintenance details",
                    height=85
                )

                # Single-line Create button

                button_space, button_col = st.columns([1, 2])

                with button_col:

                    submitted = st.form_submit_button(
                        "＋ Create Work Order",
                        type="primary",
                        use_container_width=True
                    )

                if submitted:

                    if not task.strip():

                        st.error("Please enter a maintenance task.")

                    elif not assigned_to.strip():

                        st.error("Please enter an assigned technician.")

                    else:

                        selected_alert = alert_options[
                            selected_alert_label
                        ]

                        try:

                            maintenance_db.add_work_order(
                                alert_id=selected_alert["id"],
                                task=task.strip(),
                                assigned_to=assigned_to.strip(),
                                priority=priority,
                                notes=notes.strip()
                            )

                            st.success(
                                "Work order created successfully."
                            )

                            st.rerun()

                        except Exception as error:

                            st.error(
                                f"Could not create work order: {error}"
                            )


# --------------------------------------------------
# UPDATE WORK ORDER
# --------------------------------------------------

with update_col:

    with st.container(border=True):

        st.markdown(
            '<div class="panel-title">↻ Update Work Order</div>',
            unsafe_allow_html=True
        )

        st.markdown(
            '<div class="section-description">'
            'Change the progress status of an existing maintenance task.'
            '</div>',
            unsafe_allow_html=True
        )

        if work_orders:

            order_options = {
                (
                    f"Work Order #{order['id']} | "
                    f"{order['task']} | "
                    f"{order['status']}"
                ): order
                for order in work_orders
            }

            selected_order_label = st.selectbox(
                "Select work order",
                list(order_options.keys()),
                key="selected_work_order"
            )

            selected_order = order_options[selected_order_label]

            status_options = [
                "Open",
                "In Progress",
                "Completed",
                "Cancelled"
            ]

            current_status = selected_order["status"]

            current_index = (
                status_options.index(current_status)
                if current_status in status_options
                else 0
            )

            new_status = st.selectbox(
                "New work order status",
                status_options,
                index=current_index,
                key="new_work_order_status"
            )

            status_changed = new_status != current_status

            st.write("")

            # Single-line Update button

            button_space, button_col = st.columns([1, 2])

            with button_col:

                if st.button(
                    "Update Status",
                    type="primary",
                    use_container_width=True,
                    disabled=not status_changed
                ):

                    try:

                        maintenance_db.update_work_order_status(
                            selected_order["id"],
                            new_status
                        )

                        st.success(
                            "Work order status updated successfully."
                        )

                        st.rerun()

                    except Exception as error:

                        st.error(
                            f"Could not update work order: {error}"
                        )

            if not status_changed:

                st.caption(
                    "Choose a different status to enable the update button."
                )

        else:

            st.info(
                "Create a work order before updating its status."
            )


# --------------------------------------------------
# FOOTER
# --------------------------------------------------

st.markdown(
    """
    <div class="page-footer">
        ⚙️ Work orders are stored in the independent
        milling machine SQLite database.
    </div>
    """,
    unsafe_allow_html=True
)
