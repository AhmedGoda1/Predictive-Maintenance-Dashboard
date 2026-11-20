
from pathlib import Path

import streamlit as st


# ---------------------------------------------------------
# PAGE CONFIGURATION
# ---------------------------------------------------------

st.set_page_config(
    page_title="Milling Machine Monitor",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ---------------------------------------------------------
# PROJECT PATHS
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
IMAGE_PATH = BASE_DIR / "assets" / "milling_machine.jpg"


# ---------------------------------------------------------
# GLOBAL CSS
# ---------------------------------------------------------

st.markdown("""
<style>

/* =========================================
   MAIN APPLICATION
   ========================================= */

.stApp {
    background-color: #F3F6FA;
}

.block-container {
    padding-top: 2.5rem;
    padding-bottom: 2rem;
}


/* =========================================
   SIDEBAR BACKGROUND
   ========================================= */

section[data-testid="stSidebar"] {
    background-color: #172B43 !important;
}

section[data-testid="stSidebar"] > div {
    padding-top: 0.5rem;
}


/* =========================================
   SIDEBAR MACHINE IMAGE
   ========================================= */

section[data-testid="stSidebar"] [data-testid="stImage"] img {
    height: 90px !important;
    width: 100% !important;
    object-fit: cover !important;
    border-radius: 10px !important;
}


/* =========================================
   SIDEBAR BRANDING
   ========================================= */

.sidebar-brand-title {
    color: #FFFFFF;
    font-size: 1.1rem;
    font-weight: 700;
    line-height: 1.3;
    margin-top: 9px;
    margin-bottom: 4px;
}

.sidebar-brand-subtitle {
    color: #B8C5D6;
    font-size: 0.78rem;
    line-height: 1.4;
    margin-bottom: 8px;
}

.sidebar-brand-divider {
    border: none;
    border-top: 1px solid rgba(255,255,255,0.12);
    margin: 9px 0 12px 0;
}


/* =========================================
   NAVIGATION SECTION HEADINGS
   ========================================= */

.sidebar-section {
    color: #91A4BB;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 1.2px;
    margin: 13px 0 5px 8px;
}


/* =========================================
   NAVIGATION LINKS
   ========================================= */

section[data-testid="stSidebar"] [data-testid="stPageLink"] {
    margin-top: 1px;
    margin-bottom: 2px;
}

section[data-testid="stSidebar"] [data-testid="stPageLink"] a {
    color: #E2E8F0 !important;
    border-radius: 7px;
    padding: 7px 10px;
    min-height: 36px;
    font-size: 0.88rem;
    font-weight: 500;
    text-decoration: none;
}

section[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover {
    background-color: rgba(255,255,255,0.08) !important;
    color: #FFFFFF !important;
}

section[data-testid="stSidebar"] [data-testid="stPageLink"] span {
    color: #CBD5E1 !important;
}


/* =========================================
   SIDEBAR COLLAPSE / EXPAND BUTTON
   ========================================= */

/* Sidebar header */
section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {
    background-color: #172B43 !important;
}

/* Collapse and expand buttons */
section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] button,
button[data-testid="stSidebarCollapseButton"],
button[data-testid="stSidebarExpandButton"] {

    color: #FFFFFF !important;

    background-color: #334B66 !important;

    border: 1px solid #71869E !important;

    border-radius: 7px !important;

    opacity: 1 !important;

    box-shadow: 0 1px 4px rgba(0,0,0,0.25) !important;

}

/* SVG icons */
section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] button svg,
button[data-testid="stSidebarCollapseButton"] svg,
button[data-testid="stSidebarExpandButton"] svg {

    color: #FFFFFF !important;

    fill: #FFFFFF !important;

    stroke: #FFFFFF !important;

    opacity: 1 !important;

}

/* SVG icon paths */
section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] button svg path,
button[data-testid="stSidebarCollapseButton"] svg path,
button[data-testid="stSidebarExpandButton"] svg path {

    stroke: #FFFFFF !important;

    stroke-width: 2.2px !important;

}

/* Hover effect */
section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] button:hover,
button[data-testid="stSidebarCollapseButton"]:hover,
button[data-testid="stSidebarExpandButton"]:hover {

    background-color: #45617F !important;

    border-color: #CBD5E1 !important;

}


/* =========================================
   GENERAL BUTTONS
   ========================================= */

.stButton > button,
.stFormSubmitButton > button {
    border-radius: 8px;
    font-weight: 600;
}

</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# PAGE DEFINITIONS
# ---------------------------------------------------------

overview_page = st.Page(
    str(BASE_DIR / "pages" / "overview.py"),
    title="Overview",
    url_path="overview"
)

monitoring_page = st.Page(
    str(BASE_DIR / "pages" / "machine_monitoring.py"),
    title="Machine Monitoring",
    url_path="machine-monitoring"
)

prediction_page = st.Page(
    str(BASE_DIR / "pages" / "ai_prediction.py"),
    title="AI Prediction",
    url_path="ai-prediction"
)

alerts_page = st.Page(
    str(BASE_DIR / "pages" / "alert_centre.py"),
    title="Alert Centre",
    url_path="alert-centre"
)

work_orders_page = st.Page(
    str(BASE_DIR / "pages" / "work_orders.py"),
    title="Work Orders",
    url_path="work-orders"
)

analytics_page = st.Page(
    str(BASE_DIR / "pages" / "lean_analytics.py"),
    title="Lean Analytics",
    url_path="lean-analytics"
)


# ---------------------------------------------------------
# REGISTER NAVIGATION
# ---------------------------------------------------------

pages = [
    overview_page,
    monitoring_page,
    prediction_page,
    alerts_page,
    work_orders_page,
    analytics_page
]

navigation = st.navigation(
    pages,
    position="hidden"
)


# ---------------------------------------------------------
# CUSTOM SIDEBAR
# ---------------------------------------------------------

with st.sidebar:

    # Machine photograph
    if IMAGE_PATH.exists():
        st.image(
            str(IMAGE_PATH),
            use_container_width=True
        )
    else:
        st.warning("Milling machine image not found.")

    # Branding
    st.markdown("""
    <div class="sidebar-brand-title">
        Milling Tool-Wear Monitoring
    </div>

    <div class="sidebar-brand-subtitle">
        IoT Predictive Maintenance Prototype
    </div>

    <hr class="sidebar-brand-divider">
    """, unsafe_allow_html=True)

    # MONITORING
    st.markdown(
        '<div class="sidebar-section">MONITORING</div>',
        unsafe_allow_html=True
    )

    st.page_link(
        overview_page,
        label="Overview",
        icon=":material/dashboard:"
    )

    st.page_link(
        monitoring_page,
        label="Machine Monitoring",
        icon=":material/monitor_heart:"
    )

    st.page_link(
        prediction_page,
        label="AI Prediction",
        icon=":material/psychology:"
    )

    # MAINTENANCE
    st.markdown(
        '<div class="sidebar-section">MAINTENANCE</div>',
        unsafe_allow_html=True
    )

    st.page_link(
        alerts_page,
        label="Alert Centre",
        icon=":material/warning:"
    )

    st.page_link(
        work_orders_page,
        label="Work Orders",
        icon=":material/build:"
    )

    # ANALYTICS
    st.markdown(
        '<div class="sidebar-section">ANALYTICS</div>',
        unsafe_allow_html=True
    )

    st.page_link(
        analytics_page,
        label="Lean Analytics",
        icon=":material/analytics:"
    )


# ---------------------------------------------------------
# RUN APPLICATION
# ---------------------------------------------------------

navigation.run()
