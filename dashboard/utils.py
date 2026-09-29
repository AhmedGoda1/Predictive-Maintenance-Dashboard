import plotly.express as px
import plotly.graph_objects as go

def plot_telemetry_trends(df, asset_id, feature="temperature_c", threshold=None):
    """Creates an interactive time-series line plot with optional warning threshold."""
    filtered_df = df[df["asset_id"] == asset_id]

    feature_labels = {
        "temperature_c": "Temperature (°C)",
        "vibration_mm_s": "Vibration Velocity (mm/s)",
        "pressure_psi": "Pressure (PSI)"
    }

    y_title = feature_labels.get(feature, feature)

    fig = px.line(
        filtered_df,
        x="timestamp",
        y=feature,
        title=f"{y_title} Over Time - {asset_id}",
        labels={"timestamp": "Time", feature: y_title},
        markers=True
    )

    if threshold is not None:
        fig.add_hline(
            y=threshold,
            line_dash="dash",
            line_color="red",
            annotation_text=f"Threshold ({threshold})",
            annotation_position="bottom right"
        )

    fig.update_layout(
        hovermode="x unified",
        margin=dict(l=20, r=20, t=40, b=20),
        template="plotly_white"
    )

    return fig

def plot_health_gauge(health_score, asset_id):
    """Creates a circular gauge chart showing equipment health score."""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=health_score,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': f"Health Index ({asset_id})"},
        gauge={
            'axis': {'range': [0, 100]},
            'bar': {'color': "#1e293b"},
            'steps': [
                {'range': [0, 60], 'color': '#f87171'},   # Red (Critical)
                {'range': [60, 80], 'color': '#fbbf24'},  # Yellow (Warning)
                {'range': [80, 100], 'color': '#34d399'}  # Green (Healthy)
            ],
        }
    ))
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20), height=250)
    return fig

def plot_failure_risk_bar(df_preds):
    """Creates a horizontal bar chart ranking equipment by failure probability."""
    sorted_df = df_preds.sort_values(by="failure_prob", ascending=True)

    color_map = {"Healthy": "#10b981", "Warning": "#f59e0b", "Critical": "#ef4444"}

    fig = px.bar(
        sorted_df,
        x="failure_prob",
        y="asset_id",
        orientation="h",
        color="status",
        color_discrete_map=color_map,
        title="Asset Failure Probability (Next 30 Days)",
        labels={"failure_prob": "Probability of Failure", "asset_id": "Asset ID"}
    )
    fig.update_xaxes(tickformat=".0%")
    fig.update_layout(template="plotly_white", margin=dict(l=20, r=20, t=40, b=20))
    return fig