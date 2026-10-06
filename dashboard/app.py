import hashlib
import os
import sys
import time
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent


def _code_version() -> str:
    """Drops this project's modules from memory when any of its source files changed; returns a version id.

    Streamlit hot-reloads only the modules next to this script, not the `pdm` package in the repository
    root. After a deployment that updates both without restarting the process, the new dashboard code
    would otherwise run against the old `pdm` modules still held in memory (AttributeError on new
    functions). The version id keys the data caches, so cached data never outlives the code that made it.
    """
    files = sorted([*(_ROOT / "pdm").rglob("*.py"), *_HERE.glob("*.py")])
    signature = tuple((str(f), f.stat().st_mtime_ns) for f in files)
    previous = getattr(sys, "_dashboard_code_signature", None)
    sys._dashboard_code_signature = signature
    if previous is not None and previous != signature:
        ours = {f.stem for f in _HERE.glob("*.py")} - {"app"}
        for name in list(sys.modules):
            if name == "pdm" or name.startswith("pdm.") or name in ours:
                del sys.modules[name]
    return hashlib.md5(repr(signature).encode()).hexdigest()[:12]


CODE_VERSION = _code_version()

import asset_view  # noqa: E402  (imported after the check above so they are always fresh)
import data_source as ds  # noqa: E402
import fleet_view  # noqa: E402
import live_feed  # noqa: E402

st.set_page_config(page_title="Predictive Maintenance Dashboard", page_icon="🛠️", layout="wide")


@st.cache_data(show_spinner="Preparing database...")
def get_fleet(code_version: str, data_stamp: tuple):
    return ds.load_fleet()


@st.cache_data(show_spinner="Loading asset...")
def get_asset(asset_id: str, code_version: str, data_stamp: tuple):
    return ds.load_asset(asset_id)


@st.cache_resource
def get_feed(code_version: str):
    return live_feed.FeedController()


@st.cache_resource
def get_ingestor(code_version: str):
    """The MQTT ingestion subscriber of this process, or None when no broker is configured."""
    return live_feed.start_ingestor()


REFRESH_SECONDS = float(os.environ.get("PDM_REFRESH_SECONDS", 3))     # 0 turns auto-refresh off (used by tests)

with st.spinner("Preparing database..."):
    STAMP = ds.data_stamp()          # builds the database first if it is missing or outdated
fleet = get_fleet(CODE_VERSION, STAMP)
feed = get_feed(CODE_VERSION)
ingestor = get_ingestor(CODE_VERSION)
asset_ids = list(fleet.assets["asset_id"])
names = dict(zip(fleet.assets["asset_id"], fleet.assets["name"]))

st.session_state.setdefault("view", "Fleet")
# the first asset opened from the sidebar is the one that needs attention most
st.session_state.setdefault("selected_asset", ds.snapshot(fleet, 1.0)["asset_id"].iloc[0])

st.sidebar.title("🛠️ Maintenance Portal")
st.sidebar.radio("View", ["Fleet", "Asset detail"], key="view")
st.sidebar.markdown("---")

def live_panel():
    """Start / stop the simulated sensor feed and choose whether the page refreshes by itself."""
    with st.sidebar.expander("Live data (MQTT)", expanded=feed.running or live_feed.has_live_assets()):
        if ingestor is None:
            st.caption("⚪ This app does not run its own MQTT subscriber (PDM_MQTT_HOST is not set). Readings from a "
                       "separately running ingestion service still appear, because they share the database. "
                       "The demo feed below writes straight into the ingestion code.")
        else:
            info = ingestor.status()
            st.caption(f"{'🟢 connected to' if info['connected'] else '🔴 not connected to'} `{info['broker']}` · "
                       f"{info['processed']} messages processed")
            if info["last_error"] and not info["connected"]:
                st.warning(info["last_error"])
            st.caption("Publish to `pdm/v1/assets/<id>/readings` (see the README for the payload).")
        st.markdown("**Demo feed**: simulated sensors, shared by everyone using this app.")
        engines = st.slider("Engines", 1, 6, 4, key="feed_engines", disabled=feed.running)
        motor = st.checkbox("Also the DC motor", key="feed_motor", disabled=feed.running)
        speed = st.select_slider("Speed (seconds per reading)", options=[0.25, 0.5, 1.0, 2.0], value=1.0,
                                 key="feed_speed", disabled=feed.running)
        start, stop = st.columns(2)
        if start.button("▶ Start", disabled=feed.running, width="stretch", key="feed_start"):
            feed.start(engines, motor, speed, 1)
            st.session_state["live_refresh"] = True
            st.rerun()
        if stop.button("⏹ Stop", disabled=not feed.running, width="stretch", key="feed_stop"):
            feed.stop()
            st.rerun()
        status = feed.status()
        if status["total"]:
            sent, total = sum(status["sent"].values()), sum(status["total"].values())
            st.progress(min(sent / total, 1.0), text=f"{sent} of {total} readings sent"
                        + (" · finished" if status["done"] else "" if feed.running else " · stopped"))
        if status["errors"]:
            st.warning(f"{status['errors']} send error(s). Last: {status['last_error']}")
        if st.button("Remove simulated assets", width="stretch", key="feed_clear",
                     disabled=not live_feed.has_live_assets()):
            feed.clear()
            st.rerun()
        if REFRESH_SECONDS > 0:
            st.checkbox(f"Refresh every {REFRESH_SECONDS:g} s", key="live_refresh",
                        help="Reloads the page to show readings as they arrive.")


if st.session_state["view"] == "Fleet":
    st.sidebar.info("Recorded test runs, scored as if they were live assets. Select a row in the priority table "
                    "to open an asset.")
    fleet_view.render(fleet)
    live_panel()
else:
    current = st.session_state["selected_asset"]
    asset_id = st.sidebar.selectbox(
        "Asset", asset_ids, index=asset_ids.index(current) if current in asset_ids else 0,
        format_func=lambda a: f"{names[a]} ({a})")
    st.session_state["selected_asset"] = asset_id
    asset_view.render(get_asset(asset_id, CODE_VERSION, STAMP))
    live_panel()

if REFRESH_SECONDS > 0 and st.session_state.get("live_refresh"):
    time.sleep(REFRESH_SECONDS)
    st.rerun()
