import hashlib
import sys
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

st.set_page_config(page_title="Predictive Maintenance Dashboard", page_icon="🛠️", layout="wide")


@st.cache_data(show_spinner="Preparing database...")
def get_fleet(code_version: str):
    return ds.load_fleet()


@st.cache_data(show_spinner="Loading asset...")
def get_asset(asset_id: str, code_version: str):
    return ds.load_asset(asset_id)


fleet = get_fleet(CODE_VERSION)
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
    asset_view.render(get_asset(asset_id, CODE_VERSION))
