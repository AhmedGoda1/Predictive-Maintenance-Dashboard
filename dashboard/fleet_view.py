"""Fleet overview: which assets need attention, across asset types."""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

import components
import data_source as ds
import utils

METRICS_FILE = ds.ROOT / "models" / "cmapss_metrics.json"
ALL_TYPES = "All types"


def _open_selected():
    """Row click in the priority table: jump to that asset's detail page at the snapshot position."""
    sel = st.session_state.get("fleet_table")
    rows = sel.selection.rows if sel else []
    if rows:
        asset_id = st.session_state["_fleet_rows"][rows[0]]
        st.session_state["selected_asset"] = asset_id
        st.session_state["view"] = "Asset detail"
        st.session_state[f"pos_{asset_id}"] = st.session_state["_fleet_pos"][asset_id]
        st.session_state[f"playing_{asset_id}"] = False


def _rul_text(row) -> str:
    if pd.isna(row["rul_pred"]):
        return "n/a"
    text = ds.format_rul(row["rul_pred"], row["type_id"])
    if pd.notna(row["rul_low"]) and pd.notna(row["rul_high"]):
        factor, _ = ds.unit_factor(row["type_id"])
        text += f"  ({row['rul_low'] * factor:.0f}-{row['rul_high'] * factor:.0f})"
    return text


def _priority_table(snap: pd.DataFrame):
    view = pd.DataFrame({
        "Status": snap["status"].map(utils.status_label),
        "Asset": snap["asset_id"],
        "Type": snap["type_name"],
        "Health index": snap["health_score"],
        "Estimated RUL (80% range)": snap.apply(_rul_text, axis=1),
        "Actual remaining": snap.apply(lambda r: ds.format_amount(r["rul_true"], r["type_id"]), axis=1),
        "Produced by": snap["method"],
        "Open alerts": snap["open_alerts"],
    })
    st.session_state["_fleet_rows"] = list(snap["asset_id"])
    st.session_state["_fleet_pos"] = dict(zip(snap["asset_id"], snap["position"]))
    st.dataframe(
        view, hide_index=True, width="stretch", key="fleet_table", on_select=_open_selected,
        selection_mode="single-row", height=min(38 * len(view) + 40, 440),
        column_config={
            "Health index": st.column_config.ProgressColumn("Health index", min_value=0, max_value=100, format="%d"),
            "Open alerts": st.column_config.NumberColumn("Open alerts", format="%d"),
        },
    )
    st.caption("Select a row to open the asset. Actual remaining life is known only because these are recorded "
               "test runs; a live asset would not have it.")


def _rul_charts(snap: pd.DataFrame, show_actual: bool):
    """One RUL chart per asset type (units differ between types, so they never share an axis)."""
    for type_id, part in snap.groupby("type_id", sort=True):
        name = part["type_name"].iloc[0]
        with_rul = part[part["rul_pred"].notna()]
        if with_rul.empty:
            st.info(f"{name}: no RUL estimate available, only the health index.")
        elif len(with_rul) == 1:
            r = with_rul.iloc[0]
            st.markdown(f"**{name}** · `{r['asset_id']}`")
            c1, c2 = st.columns(2)
            c1.metric("Estimated RUL", ds.format_rul(r["rul_pred"], type_id), help=f"Produced by: {r['method']}")
            c2.metric("Actual remaining", ds.format_amount(r["rul_true"], type_id))
            st.caption(f"Only one {name} is monitored, so there is nothing to rank; see the asset page.")
        else:
            st.plotly_chart(utils.plot_fleet_rul(snap, type_id, show_actual), width="stretch")


def _alerts_tab(snap: pd.DataFrame):
    open_ = snap[snap["open_alerts"] > 0]
    if open_.empty:
        st.success("No open alerts at this snapshot.")
        return
    st.dataframe(pd.DataFrame({
        "Level": open_["latest_level"].map(utils.status_label),
        "Asset": open_["asset_id"],
        "Latest alert": open_["latest_alert"], "Suggested action": open_["latest_action"],
        "Alerts so far": open_["open_alerts"],
    }), hide_index=True, width="stretch")
    st.caption("The newest alert of each asset up to the snapshot. Open an asset for its full alert log and work orders.")


def _models_tab(fleet: ds.Fleet):
    st.subheader("Model registry")
    st.dataframe(ds.models_table(fleet), hide_index=True, width="stretch")
    st.caption("A learned model is validated on assets it never saw. The experimental single-run estimate cannot be: "
               "only one asset of its type exists.")
    if METRICS_FILE.exists():
        st.subheader("Learned RUL model validated on four engine fleets (NASA C-MAPSS)")
        results = json.loads(METRICS_FILE.read_text())
        regimes = {"FD001": "1 / 1", "FD002": "6 / 1", "FD003": "1 / 2", "FD004": "6 / 2"}
        table = pd.DataFrame([{
            "Subset": s, "Conditions / fault modes": regimes.get(s, ""),
            "Train / test engines": f"{r['n_train_engines']} / {r['n_test_engines']}",
            "RMSE (cycles)": r["test"]["rmse"], "NASA score": r["test"]["nasa_score"],
            "Coverage (nominal 0.80)": r["test"]["coverage"],
            "Constant guess RMSE": r["baselines"]["constant"]["rmse"],
            "Age-only RMSE": r["baselines"]["age_only"]["rmse"],
        } for s, r in sorted(results.items())])
        st.dataframe(table, hide_index=True, width="stretch", column_config={
            "RMSE (cycles)": st.column_config.NumberColumn(format="%.1f"),
            "Constant guess RMSE": st.column_config.NumberColumn(format="%.1f"),
            "Age-only RMSE": st.column_config.NumberColumn(format="%.1f"),
            "NASA score": st.column_config.NumberColumn(format="%.0f"),
            "Coverage (nominal 0.80)": st.column_config.NumberColumn(format="%.2f")})
        st.caption("Predicted at the last reading of every held-out test engine. Only FD001 is loaded into this "
                   "fleet view. Generalisation is shown across engines of one type, not across asset types.")
    st.subheader("Data sources")
    st.markdown(
        "- **Turbofan engines:** A. Saxena and K. Goebel (2008), *Turbofan Engine Degradation Simulation Data Set*, "
        "NASA Ames Prognostics Data Repository (public domain). One cycle is shown as one hour on a synthetic timeline.\n"
        "- **Brushed DC motor:** A. Reñones (2020), *F.A.I.R. open dataset of brushed DC motor faults*, CARTIF, "
        "[zenodo.org/records/4314249](https://zenodo.org/records/4314249), CC-BY-4.0. One motor run to failure."
    )


def render(fleet: ds.Fleet):
    st.title("Fleet overview")

    # filters in one row above everything they scope; restore their values after a view switch
    st.session_state.setdefault("fleet_pct", st.session_state.get("_fleet_pct", 100))
    st.session_state.setdefault("fleet_type", st.session_state.get("_fleet_type", ALL_TYPES))
    st.session_state.setdefault("fleet_actual", st.session_state.get("_fleet_actual", True))
    type_names = {t: ds.registry.get_type(t).name for t in sorted(fleet.assets["type_id"].unique())}
    f1, f2, f3 = st.columns([1, 2, 1.2])
    choice = f1.selectbox("Asset type", [ALL_TYPES, *type_names], format_func=lambda t: type_names.get(t, t),
                          key="fleet_type")
    pct = f2.slider("Snapshot: share of each asset's recorded life", 0, 100, key="fleet_pct", format="%d%%",
                    help="Replays the fleet. 100% is each asset's latest reading; lower values show earlier states.")
    show_actual = f3.checkbox("Show actual remaining life (test data)", key="fleet_actual")
    st.session_state.update(_fleet_pct=pct, _fleet_type=choice, _fleet_actual=show_actual)

    snap = ds.snapshot(fleet, pct / 100)
    if choice != ALL_TYPES:
        snap = snap[snap["type_id"] == choice].reset_index(drop=True)

    components.render_fleet_kpis(ds.status_counts(snap), len(snap))
    st.markdown("---")

    tab_status, tab_alerts, tab_models = st.tabs(["📋 Maintenance priority", "🚨 Open alerts", "🧠 Models & data"])
    with tab_status:
        _priority_table(snap)
        left, right = st.columns(2)
        with left:
            st.plotly_chart(utils.plot_fleet_health(snap), width="stretch")
        with right:
            _rul_charts(snap, show_actual)
    with tab_alerts:
        _alerts_tab(snap)
    with tab_models:
        _models_tab(fleet)
