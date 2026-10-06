"""Charts for the fleet and asset views.

Colour rules: status colours (good / warning / critical) are reserved for status and always come with
an icon and a label; the single data series uses one categorical hue; the grid is a recessive hairline.
RUL is never drawn on a shared axis across asset types, because their units differ (cycles vs. minutes).
"""
import numpy as np
import plotly.graph_objects as go

import data_source as ds

STATUS_COLORS = {"Healthy": "#0ca30c", "Warning": "#fab219", "Critical": "#d03b3b", "Failed": "#7d7c78"}
STATUS_ICONS = {"Healthy": "🟢", "Warning": "🟡", "Critical": "🔴", "Failed": "⚫"}
STATUS_SYMBOLS = {"Healthy": "circle", "Warning": "diamond", "Critical": "square", "Failed": "x"}
SERIES = "#2a78d6"            # categorical slot 1: the one data series
NEUTRAL = "#8a8985"           # reference / ground-truth marks
GRID = "rgba(128,128,128,0.22)"
BAND_ALPHA = 0.10


def status_label(status: str) -> str:
    return f"{STATUS_ICONS.get(status, '')} {status}"


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{alpha})"


def _style(fig, title, height=330, legend=True):
    fig.update_layout(
        title=dict(text=title, font=dict(size=15)), height=height, hovermode="closest",
        margin=dict(l=20, r=20, t=50, b=20), barcornerradius=4,
        showlegend=legend, legend=dict(orientation="h", y=-0.22, x=0),
    )
    fig.update_xaxes(showgrid=True, gridcolor=GRID, gridwidth=1, zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, gridwidth=1, zeroline=False)
    return fig


# ---------------------------------------------------------------- fleet view
def plot_fleet_health(snap):
    """Health index of every asset, worst first. Comparable across asset types (0-100, no unit)."""
    fig = go.Figure()
    order = list(snap["asset_id"])
    for status in ds.STATUS_RANK:
        part = snap[snap["status"] == status]
        if part.empty:
            continue
        fig.add_trace(go.Bar(
            x=part["health_score"], y=part["asset_id"], orientation="h", name=status,
            marker=dict(color=STATUS_COLORS[status]),
            # a failed asset has health 0, i.e. no bar: label it so it does not look like missing data
            text=[status.lower()] * len(part) if status == "Failed" else None, textposition="outside",
            cliponaxis=False,
            customdata=np.stack([part["name"], part["type_name"], part["top_driver"].fillna("none")], axis=1),
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>health index %{x:.0f}"
                          "<br>main driver: %{customdata[2]}<extra></extra>",
        ))
    fig.update_layout(bargap=0.45, barmode="overlay")
    fig.update_yaxes(categoryorder="array", categoryarray=order, autorange="reversed", showgrid=False, title="")
    fig.update_xaxes(range=[0, 100], tickvals=[0, 40, 70, 100], title="Health index (grid lines: Warning below 70, Critical below 40)")
    return _style(fig, "Health index by asset", height=max(260, 24 * len(snap) + 130))


def plot_fleet_rul(snap, type_id: str, show_actual: bool = True):
    """Estimated RUL with its prediction interval for the assets of ONE type, shortest first."""
    part = snap[(snap["type_id"] == type_id) & snap["rul_pred"].notna()].sort_values("rul_pred")
    factor, unit = ds.unit_factor(type_id)
    fig = go.Figure()
    for status in ds.STATUS_RANK:
        s = part[part["status"] == status]
        if s.empty:
            continue
        has_interval = s["rul_low"].notna() & s["rul_high"].notna()
        err = None
        if has_interval.any():
            err = dict(type="data", symmetric=False, thickness=1.5, width=0, color=_rgba(STATUS_COLORS[status], 0.7),
                       array=((s["rul_high"] - s["rul_pred"]).fillna(0) * factor).to_numpy(),
                       arrayminus=((s["rul_pred"] - s["rul_low"]).fillna(0) * factor).to_numpy())
        fig.add_trace(go.Scatter(
            x=s["rul_pred"] * factor, y=s["asset_id"], mode="markers", name=status,
            marker=dict(color=STATUS_COLORS[status], size=10, symbol=STATUS_SYMBOLS[status],
                        line=dict(color="rgba(255,255,255,0.9)", width=2)),
            error_x=err,
            customdata=np.stack([s["name"], s["rul_low"].fillna(np.nan) * factor, s["rul_high"].fillna(np.nan) * factor], axis=1),
            hovertemplate="<b>%{customdata[0]}</b><br>estimated %{x:.0f} " + unit +
                          "<br>80% range %{customdata[1]:.0f}-%{customdata[2]:.0f}<extra></extra>",
        ))
    if show_actual and part["rul_true"].notna().any():
        a = part[part["rul_true"].notna()]
        fig.add_trace(go.Scatter(
            x=a["rul_true"] * factor, y=a["asset_id"], mode="markers", name="Actual (known from the benchmark)",
            marker=dict(color=NEUTRAL, symbol="line-ns-open", size=16, line=dict(color=NEUTRAL, width=2.5)),
            hovertemplate="actual %{x:.0f} " + unit + "<extra></extra>",
        ))
    fig.update_yaxes(categoryorder="array", categoryarray=list(part["asset_id"]), autorange="reversed",
                     showgrid=True, title="")
    fig.update_xaxes(rangemode="tozero", title=f"Remaining useful life ({unit})")
    return _style(fig, "Estimated remaining useful life with 80% prediction interval",
                  height=max(260, 24 * len(part) + 130))


# ---------------------------------------------------------------- asset view
def _stress_segments(df, t):
    """(x0, x1) pairs, in display age units, where the asset ran in its type's overstress regime."""
    if not t.stress_channel or t.stress_channel not in df:
        return []
    over = (df[t.stress_channel] > t.stress_above).to_numpy()
    x = df["age_disp"].to_numpy()
    segs, start = [], None
    for i, flag in enumerate(over):
        if flag and start is None:
            start = x[i]
        if not flag and start is not None:
            segs.append((start, x[i - 1]))
            start = None
    if start is not None:
        segs.append((start, x[-1]))
    return segs


def _shade_stress(fig, df, t):
    segs = _stress_segments(df, t)
    for x0, x1 in segs:
        fig.add_vrect(x0=x0, x1=x1, fillcolor="rgba(138,137,133,0.20)", line_width=0, layer="below")
    if segs:   # legend entry for the shading
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name=t.stress_label,
                                 marker=dict(color="rgba(138,137,133,0.45)", size=12, symbol="square")))


def plot_health_gauge(health_score, status, t):
    """Meter showing the current health index against the type's status thresholds."""
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=health_score, domain={"x": [0, 1], "y": [0, 1]},
        title={"text": f"Health index: {status}"}, number={"suffix": " / 100", "valueformat": ".0f"},
        gauge={"axis": {"range": [0, 100]}, "bar": {"color": STATUS_COLORS.get(status, SERIES), "thickness": 0.35},
               "steps": [{"range": [0, t.warning_min], "color": _rgba(STATUS_COLORS["Critical"], 0.25)},
                         {"range": [t.warning_min, t.healthy_min], "color": _rgba(STATUS_COLORS["Warning"], 0.30)},
                         {"range": [t.healthy_min, 100], "color": _rgba(STATUS_COLORS["Healthy"], 0.25)}]},
    ))
    fig.update_layout(margin=dict(l=30, r=45, t=50, b=10), height=240)
    return fig


def plot_health_timeline(df, t, x_range):
    """Health index over the replay so far, with the status bands behind it."""
    fig = go.Figure()
    for lo, hi, status in [(0, t.warning_min, "Critical"), (t.warning_min, t.healthy_min, "Warning"),
                           (t.healthy_min, 100, "Healthy")]:
        fig.add_hrect(y0=lo, y1=hi, fillcolor=_rgba(STATUS_COLORS[status], BAND_ALPHA), line_width=0, layer="below")
    _shade_stress(fig, df, t)
    fig.add_trace(go.Scatter(x=df["age_disp"], y=df["health_score"], mode="lines", name="Health index",
                             line=dict(color=SERIES, width=2),
                             hovertemplate="%{y:.0f} / 100<extra></extra>"))
    factor, unit = ds.unit_factor(t.type_id)
    fig.update_yaxes(range=[0, 100], title="Health index", tickvals=[0, t.warning_min, t.healthy_min, 100])
    fig.update_xaxes(range=x_range, title=f"Age ({unit})")
    fig.update_layout(hovermode="x unified")
    return _style(fig, "Health index (bands: Critical / Warning / Healthy)", legend=bool(_stress_segments(df, t)))


def plot_rul(df, t, x_range):
    """Estimated RUL with its interval against the actual remaining life (when known)."""
    factor, unit = ds.unit_factor(t.type_id)
    fig = go.Figure()
    if df["rul_low_disp"].notna().any():
        fig.add_trace(go.Scatter(x=df["age_disp"], y=df["rul_high_disp"], mode="lines", line=dict(width=0),
                                 showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=df["age_disp"], y=df["rul_low_disp"], mode="lines", line=dict(width=0),
                                 fill="tonexty", fillcolor=_rgba(SERIES, 0.18), name="80% prediction interval",
                                 hoverinfo="skip"))
    if df["rul_true_disp"].notna().any():
        fig.add_trace(go.Scatter(x=df["age_disp"], y=df["rul_true_disp"], mode="lines", name="Actual remaining life",
                                 line=dict(color=NEUTRAL, width=2, dash="dot"),
                                 hovertemplate="actual %{y:.0f} " + unit + "<extra></extra>"))
    fig.add_trace(go.Scatter(x=df["age_disp"], y=df["rul_pred_disp"], mode="lines", name="Estimated RUL",
                             line=dict(color=SERIES, width=2),
                             hovertemplate="estimated %{y:.0f} " + unit + "<extra></extra>"))
    fig.update_yaxes(title=f"Remaining life ({unit})", rangemode="tozero")
    fig.update_xaxes(range=x_range, title=f"Age ({unit})")
    fig.update_layout(hovermode="x unified")
    return _style(fig, "Remaining useful life: estimate vs. actual")


def plot_sensor(df, t, channel, x_range):
    """One sensor over time, with the type's hard limits for it."""
    c = t.channel(channel)
    label = f"{c.description or channel} ({c.unit})" if c.unit else (c.description or channel)
    fig = go.Figure()
    _shade_stress(fig, df, t)
    fig.add_trace(go.Scatter(x=df["age_disp"], y=df[channel], mode="lines", name=label,
                             line=dict(color=SERIES, width=2), hovertemplate="%{y:.3g}<extra></extra>"))
    for ch, warn, crit in t.limits:
        if ch == channel:
            for value, name in [(warn, "Warning limit"), (crit, "Critical limit")]:
                fig.add_hline(y=value, line_width=1.5, line_color=STATUS_COLORS["Critical"],
                              annotation_text=f"{name} ({value:g})", annotation_position="bottom right")
    factor, unit = ds.unit_factor(t.type_id)
    fig.update_yaxes(title=label)
    fig.update_xaxes(range=x_range, title=f"Age ({unit})")
    fig.update_layout(hovermode="x unified")
    return _style(fig, f"{c.description or channel} over time", legend=bool(_stress_segments(df, t)))
