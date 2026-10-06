import pandas as pd
import plotly.graph_objects as go

STATUS_COLORS = {"Healthy": "#10b981", "Warning": "#f59e0b", "Critical": "#ef4444", "Failed": "#1e293b"}

SENSOR_LABELS = {
    "temp_motor": "Motor temperature (°C)",
    "vib_1x": "Vibration at 1x motor speed (g)",
    "vib_band_0_4k": "Vibration energy 0-4 kHz",
    "vib_band_4_8k": "Vibration energy 4-8 kHz",
    "vib_band_8_16k": "Vibration energy 8-16 kHz",
    "vib_band_16_26k": "Vibration energy 16-26 kHz",
    "current": "Current (A)",
    "voltage": "Supply voltage (V)",
    "speed_rpm": "Speed (rpm)",
}

SENSOR_THRESHOLDS = {"temp_motor": [(60.0, "Warning limit"), (70.0, "Critical limit")]}


def _with_gaps(df, max_gap_s=60):
    """Inserts an empty row inside long pauses so lines break instead of bridging them."""
    gap = df["timestamp"].diff().dt.total_seconds() > max_gap_s
    if not gap.any():
        return df
    blanks = pd.DataFrame({"timestamp": df.loc[gap, "timestamp"] - pd.Timedelta(seconds=1)})
    return pd.concat([df, blanks]).sort_values("timestamp", kind="stable")


def _layout(fig, title, x_range, height=330):
    fig.update_layout(
        title=title, hovermode="x unified", template="plotly_white",
        margin=dict(l=20, r=20, t=50, b=20), height=height,
        legend=dict(orientation="h", y=-0.2),
    )
    fig.update_xaxes(range=x_range)
    return fig


def _shade_overstress(fig, df):
    """Light shading over the periods the motor ran at the 5 V overstress supply."""
    seg_start, prev = None, None
    for t, regime in zip(df["timestamp"], df["regime"]):
        if regime == "5V" and seg_start is None:
            seg_start = t
        if regime != "5V" and seg_start is not None:
            fig.add_vrect(x0=seg_start, x1=prev, fillcolor="#94a3b8", opacity=0.15, line_width=0)
            seg_start = None
        prev = t
    if seg_start is not None:
        fig.add_vrect(x0=seg_start, x1=prev, fillcolor="#94a3b8", opacity=0.15, line_width=0)


def plot_health_gauge(health_score, status):
    """Circular gauge showing the current health index."""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=health_score,
        domain={"x": [0, 1], "y": [0, 1]},
        title={"text": f"Health Index ({status})"},
        number={"suffix": " / 100"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "#1e293b"},
            "steps": [
                {"range": [0, 40], "color": "#f87171"},
                {"range": [40, 70], "color": "#fbbf24"},
                {"range": [70, 100], "color": "#34d399"},
            ],
        },
    ))
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20), height=250)
    return fig


def plot_health_timeline(df, x_range):
    """Health index over the replay so far, with the status bands behind it."""
    df = _with_gaps(df)
    fig = go.Figure()
    for lo, hi, color in [(0, 40, "#fecaca"), (40, 70, "#fde68a"), (70, 100, "#bbf7d0")]:
        fig.add_hrect(y0=lo, y1=hi, fillcolor=color, opacity=0.35, line_width=0)
    _shade_overstress(fig, df)
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["health_score"], mode="lines",
                             name="Health index", line=dict(color="#1e293b", width=2)))
    fig.update_yaxes(range=[0, 100], title="Health index")
    return _layout(fig, "Health index (grey shading = 5 V overstress supply)", x_range)


def plot_rul(df, x_range):
    """Estimated RUL against the actual time to failure."""
    df = _with_gaps(df)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["rul_true_s"] / 60, mode="lines",
                             name="Actual time to failure", line=dict(color="#94a3b8", dash="dash")))
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["rul_pred_s"] / 60, mode="lines",
                             name="Estimated RUL", line=dict(color="#2563eb", width=2)))
    fig.update_yaxes(title="Minutes", rangemode="tozero")
    return _layout(fig, "Remaining useful life: estimate vs. actual", x_range)


def plot_sensor(df, feature, x_range):
    """Time series of one sensor with optional limit lines."""
    df = _with_gaps(df)
    fig = go.Figure()
    _shade_overstress(fig, df)
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df[feature], mode="lines",
                             name=SENSOR_LABELS[feature], line=dict(color="#2563eb")))
    for value, label in SENSOR_THRESHOLDS.get(feature, []):
        fig.add_hline(y=value, line_dash="dash", line_color="red",
                      annotation_text=f"{label} ({value:g})", annotation_position="bottom right")
    fig.update_yaxes(title=SENSOR_LABELS[feature])
    return _layout(fig, f"{SENSOR_LABELS[feature]} over time", x_range)


def plot_status_counts(health_df):
    """Bar chart of how many readings fell in each status so far."""
    counts = health_df["status"].value_counts().reindex(list(STATUS_COLORS), fill_value=0)
    fig = go.Figure(go.Bar(x=counts.values, y=counts.index, orientation="h",
                           marker_color=[STATUS_COLORS[s] for s in counts.index]))
    fig.update_layout(title="Readings per status so far", template="plotly_white",
                      margin=dict(l=20, r=20, t=50, b=20), height=250)
    return fig
