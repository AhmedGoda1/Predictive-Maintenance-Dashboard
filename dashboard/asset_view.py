"""Asset detail: health, remaining life, sensors, alerts and model information for one asset."""
import time

import pandas as pd
import streamlit as st

import components
import data_source as ds
import utils

SOURCES = {
    "NASA C-MAPSS": "A. Saxena and K. Goebel (2008), *Turbofan Engine Degradation Simulation Data Set*, NASA Ames "
                    "Prognostics Data Repository (public domain). One cycle is shown as one hour on a synthetic timeline.",
    "Zenodo 4314249": "A. Reñones (2020), *F.A.I.R. open dataset of brushed DC motor faults for testing of AI algorithms*, "
                      "CARTIF, [zenodo.org/records/4314249](https://zenodo.org/records/4314249), CC-BY-4.0.",
}


def _replay_controls(asset_id: str, n: int):
    """Play / pause / reset and a position slider in the sidebar. Returns the current position (1..n)."""
    pos_key, play_key, n_key = f"pos_{asset_id}", f"playing_{asset_id}", f"n_{asset_id}"
    st.session_state.setdefault(pos_key, n)
    st.session_state.setdefault(play_key, False)
    previous_n = st.session_state.get(n_key)
    if previous_n is not None and n > previous_n and st.session_state[pos_key] >= previous_n:
        st.session_state[pos_key] = n                  # a live asset grew while the view was at its end: keep following it
    st.session_state[n_key] = n
    play_col, reset_col = st.sidebar.columns(2)
    if play_col.button("⏸ Pause" if st.session_state[play_key] else "▶ Play", width="stretch", key=f"play_btn_{asset_id}"):
        st.session_state[play_key] = not st.session_state[play_key]
        if st.session_state[play_key] and st.session_state[pos_key] >= n:
            st.session_state[pos_key] = 1
    if reset_col.button("⏮ Reset", width="stretch", key=f"reset_btn_{asset_id}"):
        st.session_state[play_key] = False
        st.session_state[pos_key] = 1
    step = st.sidebar.select_slider("Replay speed (readings per tick)", options=[1, 2, 5, 10], value=5)
    if st.session_state[play_key]:
        st.session_state[pos_key] = min(n, st.session_state[pos_key] + step)
        if st.session_state[pos_key] >= n:
            st.session_state[play_key] = False
    st.sidebar.slider("Replay position (reading #)", 1, n, key=pos_key)
    return st.session_state[pos_key], st.session_state[play_key]


def _model_tab(a: ds.AssetData):
    t, model = a.type, a.model
    st.subheader("How the numbers are produced")
    health_text = (
        "- **Health index** compares " + ", ".join(c.description or c.name for c in t.health_channels[:4]) +
        (" and others" if len(t.health_channels) > 4 else "") +
        " with a healthy baseline taken from this asset's own first readings, and maps the deviation to 0-100.\n"
        f"- **Status:** Healthy ≥ {t.healthy_min:g}, Warning ≥ {t.warning_min:g}, Critical below that"
    )
    if t.limits:
        health_text += ", or by hard limits (" + ", ".join(f"{c} ≥ {w:g} / {k:g}" for c, w, k in t.limits) + ")"
    if t.rul_warning is not None:
        health_text += f", or when the estimated RUL falls to {t.rul_warning:g} / {t.rul_critical:g} {t.age_unit}s"
    st.markdown(health_text + ". A status change must hold for 3 readings.")

    if model is None:
        st.info("No RUL model is registered for this asset, so only the health index is shown.")
    elif model["kind"] == "learned":
        m = model["metrics"]
        st.markdown(
            f"- **Estimated RUL** comes from the learned model `{model['model_id']}`, trained on the "
            f"{m['n_train_engines']} run-to-failure engines of its training set. The shaded band is an 80% prediction "
            "interval. The estimates here are for engines the model never saw.")
        test = m["test"]
        st.subheader("Evaluation on held-out engines")
        rows = [{"": "This model", "RMSE": test["rmse"], "MAE": test["mae"], "NASA score": test["nasa_score"]}]
        for name, label in [("constant", "Constant guess (training mean)"), ("age_only", "Age-only model")]:
            b = m["baselines"][name]
            rows.append({"": label, "RMSE": b["rmse"], "MAE": b["mae"], "NASA score": b["nasa_score"]})
        st.dataframe(pd.DataFrame(rows).set_index(""), width="stretch",
                     column_config={"RMSE": st.column_config.NumberColumn(format="%.1f"),
                                    "MAE": st.column_config.NumberColumn(format="%.1f"),
                                    "NASA score": st.column_config.NumberColumn(format="%.0f")})
        st.caption(f"Errors in {t.age_unit}s at the last reading of {test['n']} test engines. The NASA score penalises "
                   "late predictions harder than early ones (lower is better).")
        c1, c2 = st.columns(2)
        c1.metric("Interval coverage (nominal 80%)", f"{test['coverage']:.0%}",
                  help="Share of test engines whose true remaining life fell inside the interval. An interval whose "
                       "upper bound reaches the training cap counts as covering any longer life.")
        c2.metric("Strict coverage", f"{test['coverage_strict']:.0%}", help="Counting the cap strictly.")
    else:
        m = model["metrics"]
        st.markdown("- **Estimated RUL** is an *experimental* random forest on smoothed sensors plus accumulated time "
                    "at the overstress supply. Each block of readings is predicted by a model that never saw it.")
        table = pd.DataFrame({
            "Evaluation": ["Blocked cross-validation", "Forward in time (train first 75%, test last 25%)"],
            "Model": [m["rul_mae_blocked_cv"], m["rul_mae_forward"]],
            "Always predict the training mean": [m["rul_mae_mean_baseline"], m["rul_mae_mean_baseline_forward"]],
        }).set_index("Evaluation")
        st.dataframe(table.map(lambda s: ds.format_amount(s, t.type_id, 1)), width="stretch")
        st.warning("**Limitation:** only one run of this asset type exists, so the estimate is evaluated on that single "
                   "run and says nothing about other assets. It is indicative only and has no prediction interval.")

    st.subheader("Data source")
    source = next((text for key, text in SOURCES.items() if (a.asset["source"] or "").startswith(key)), a.asset["source"])
    st.markdown(source)


def _not_scored_yet(a: ds.AssetData):
    """Page of an asset that has no health scores: no readings yet, or still learning its baseline."""
    t, data, n = a.type, a.data, len(a.data)
    st.title(a.asset["name"])
    st.caption(f"{t.name} · `{a.asset['asset_id']}`" + (" · live feed" if a.asset["metadata"].get("live") else ""))
    if n == 0:
        st.info("No readings have arrived for this asset yet.")
        return
    st.info(f"⚪ Learning the healthy baseline: {n} of {t.baseline_readings} readings received. "
            "Health, status and remaining life appear once there are enough readings to compare against.")
    st.progress(min(n / t.baseline_readings, 1.0))
    cols = ["age", *[c for c in t.condition_names if c in data], *[c for c in t.sensor_names if c in data][:6]]
    st.dataframe(data[["ts", *cols]].tail(10).iloc[::-1], hide_index=True, width="stretch")


def render(a: ds.AssetData):
    t, data = a.type, a.data
    n = len(data)
    asset_id = a.asset["asset_id"]
    if n == 0 or data["health_score"].isna().all():
        _not_scored_yet(a)
        return
    pos, playing = _replay_controls(asset_id, n)
    seen = data.iloc[:pos]
    current = seen.iloc[-1]
    x_range = [data["age_disp"].min(), data["age_disp"].max()]
    _, unit = ds.unit_factor(t.type_id)

    st.title(a.asset["name"])
    st.caption(f"{t.name} · `{asset_id}`" + (" · **live feed**" if a.asset["metadata"].get("live") else "") +
               f" · estimate produced by: **{a.method}** · "
               f"reading {pos} of {n} at age {current['age_disp']:.0f} {unit}"
               + (f" · {t.stress_label}" if t.stress_channel and current.get(t.stress_channel, 0) > t.stress_above else ""))
    components.render_kpi_row(current, t.type_id, a.method)
    st.markdown("---")

    tab_overview, tab_sensors, tab_alerts, tab_model = st.tabs(
        ["📊 Health Overview", "🔍 Sensor Inspector", "🚨 Alerts & Actions", "🧠 Model & Data"])

    with tab_overview:
        left, right = st.columns([3, 1])
        left.plotly_chart(utils.plot_health_timeline(seen, t, x_range), width="stretch")
        right.plotly_chart(utils.plot_health_gauge(current["health_score"], current["status"], t), width="stretch")
        st.plotly_chart(utils.plot_rul(seen, t, x_range), width="stretch")
        if t.rul_cap and a.model is not None and a.model["kind"] == "learned":
            st.caption(f"The estimate is capped at {t.rul_cap:g} {unit}: while an asset is far from failure, its remaining "
                       "life cannot be read from the sensors, so the model only says \"at least that much\".")

    with tab_sensors:
        sensors = [c for c in t.sensor_names if c in data and data[c].notna().any()]
        default = next((c.name for c in t.health_channels if c.name in sensors), sensors[0])
        channel = st.selectbox("Select sensor:", sensors, index=sensors.index(default),
                               format_func=lambda c: f"{c}: {t.channel(c).description}" if t.channel(c).description else c,
                               key=f"sensor_{asset_id}")
        st.plotly_chart(utils.plot_sensor(seen, t, channel, x_range), width="stretch")
        with st.expander("Table view: latest readings"):
            cols = ["age_disp", *[c for c in t.condition_names if c in data], channel, "health_score", "status"]
            table = seen[cols].tail(15).iloc[::-1].rename(columns={"age_disp": f"age ({unit})"})
            st.dataframe(table, hide_index=True, width="stretch")

    with tab_alerts:
        st.subheader("Maintenance Dispatch & Alert Log")
        active = a.alerts[a.alerts["ts"] <= current["ts"]]
        if active.empty:
            st.success("No alerts so far. The asset is operating within healthy parameters.")
        for _, row in active.iterrows():
            with st.expander(f"{utils.STATUS_ICONS.get(row['status_level'], '⚠️')} {row['ts']:%Y-%m-%d %H:%M} · "
                             f"{row['status_level']} · {row['detected_issue']}",
                             expanded=row["alert_id"] == active.iloc[0]["alert_id"]):
                st.write(f"**Detected issue:** {row['detected_issue']}")
                st.write(f"**Suggested action:** {row['suggested_action']}")
                if st.button("Dispatch Work Order", key=f"btn_{asset_id}_{row['alert_id']}"):
                    st.success(f"Work order created for {asset_id}. Technician notified.")

    with tab_model:
        _model_tab(a)

    if playing:
        time.sleep(0.5)
        st.rerun()
