import streamlit as st

import asset_view
import data_source as ds
import fleet_view

st.set_page_config(page_title="Predictive Maintenance Dashboard", page_icon="🛠️", layout="wide")


@st.cache_data(show_spinner="Preparing database...")
def get_fleet():
    return ds.load_fleet()


@st.cache_data(show_spinner="Loading asset...")
def get_asset(asset_id: str):
    return ds.load_asset(asset_id)


fleet = get_fleet()
asset_ids = list(fleet.assets["asset_id"])
names = dict(zip(fleet.assets["asset_id"], fleet.assets["name"]))

st.session_state.setdefault("view", "Fleet")
# the first asset opened from the sidebar is the one that needs attention most
st.session_state.setdefault("selected_asset", ds.snapshot(fleet, 1.0)["asset_id"].iloc[0])

st.sidebar.title("🛠️ Maintenance Portal")
st.sidebar.radio("View", ["Fleet", "Asset detail"], key="view")
st.sidebar.markdown("---")

if st.session_state["view"] == "Fleet":
    st.sidebar.info("Recorded test runs, scored as if they were live assets. Select a row in the priority table "
                    "to open an asset.")
    fleet_view.render(fleet)
else:
    current = st.session_state["selected_asset"]
    asset_id = st.sidebar.selectbox(
        "Asset", asset_ids, index=asset_ids.index(current) if current in asset_ids else 0,
        format_func=lambda a: f"{names[a]} ({a})")
    st.session_state["selected_asset"] = asset_id
    asset_view.render(get_asset(asset_id))
