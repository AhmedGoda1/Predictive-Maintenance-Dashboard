
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scipy.io import loadmat


# ==================================================
# 1. PATHS
# ==================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_PATH = (
    BASE_DIR
    / "Data_Milling_Machine"
    / "mill.mat"
)

FEATURE_PATH = (
    BASE_DIR
    / "database"
    / "milling_features.csv"
)

MODEL_PATH = (
    BASE_DIR
    / "models"
    / "milling_wear_model.joblib"
)


# ==================================================
# 2. PAGE STYLING
# ==================================================

st.markdown(
    """
    <style>

    .main-header {
        font-size: 2rem;
        font-weight: 750;
        color: #172B43;
        letter-spacing: -0.7px;
        margin-bottom: 3px;
    }

    .section-heading {
        color: #172B43;
        font-weight: 700;
        font-size: 1.15rem;
        margin-bottom: 5px;
    }

    .section-description {
        color: #64748B;
        font-size: 0.88rem;
        margin-bottom: 12px;
    }

    /* KPI cards */

    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 15px;
        margin-top: 12px;
        margin-bottom: 12px;
    }

    .kpi-card {
        position: relative;
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 17px 18px 16px 20px;
        min-height: 112px;
        box-shadow: 0 2px 7px rgba(15, 23, 42, 0.035);
        overflow: hidden;
    }

    .kpi-card::before {
        content: "";
        position: absolute;
        left: 0;
        top: 0;
        bottom: 0;
        width: 4px;
        background: var(--accent);
    }

    .kpi-top {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        margin-bottom: 12px;
    }

    .kpi-label {
        color: #64748B;
        font-size: 0.79rem;
        font-weight: 600;
        line-height: 1.35;
    }

    .kpi-icon {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 32px;
        height: 32px;
        flex-shrink: 0;
        border-radius: 8px;
        background: var(--icon-bg);
        color: var(--accent);
        font-size: 1.15rem;
        font-weight: 700;
    }

    .kpi-value {
        color: #172B43;
        font-size: 1.55rem;
        font-weight: 750;
        line-height: 1.2;
        letter-spacing: -0.4px;
        overflow-wrap: anywhere;
    }

    /* Information banner */

    .info-banner {
        display: flex;
        align-items: flex-start;
        gap: 12px;
        background: #EFF6FF;
        border: 1px solid #BFDBFE;
        border-radius: 10px;
        padding: 13px 16px;
        margin-top: 13px;
        margin-bottom: 8px;
    }

    .info-banner-icon {
        color: #2563EB;
        font-size: 1.15rem;
        font-weight: 700;
    }

    .info-banner-text {
        color: #1E40AF;
        font-size: 0.87rem;
        line-height: 1.55;
    }

    /* Model limitations */

    .limitation-card {
        background: #F8FAFC;
        border: 1px solid #CBD5E1;
        border-left: 4px solid #D97706;
        border-radius: 11px;
        padding: 17px 20px;
        margin-top: 10px;
        margin-bottom: 12px;
    }

    .limitation-title {
        color: #172B43;
        font-size: 0.98rem;
        font-weight: 700;
        margin-bottom: 10px;
    }

    .limitation-list {
        color: #475569;
        font-size: 0.87rem;
        line-height: 1.75;
        padding-left: 20px;
        margin-bottom: 0;
    }

    .limitation-list li {
        margin-bottom: 4px;
    }

    @media (max-width: 700px) {
        .kpi-grid {
            grid-template-columns: 1fr;
        }
    }

    </style>
    """,
    unsafe_allow_html=True
)


# ==================================================
# 3. HELPER: KPI CARDS
# ==================================================

def render_kpi_cards(cards):

    html = '<div class="kpi-grid">'

    for card in cards:

        html += f"""
        <div class="kpi-card"
             style="--accent:{card['accent']};
                    --icon-bg:{card['icon_bg']};">

            <div class="kpi-top">
                <div class="kpi-label">{card['label']}</div>
                <div class="kpi-icon">{card['icon']}</div>
            </div>

            <div class="kpi-value">{card['value']}</div>

        </div>
        """

    html += "</div>"

    st.html(html)


# ==================================================
# 4. LOAD DATA
# ==================================================

@st.cache_data
def load_metadata(path):

    experiments = loadmat(path)["mill"]

    metadata = []

    for i in range(experiments.shape[1]):

        record = experiments[0, i]

        def get_value(field):
            return float(
                np.asarray(record[field]).squeeze()
            )

        metadata.append({
            "Experiment": i + 1,
            "Case": get_value("case"),
            "Run": get_value("run"),
            "Tool Wear (VB)": get_value("VB"),
            "Time": get_value("time"),
            "DOC": get_value("DOC"),
            "Feed": get_value("feed"),
            "Material": get_value("material"),
        })

    return pd.DataFrame(metadata)


@st.cache_data
def load_feature_table(path):

    return pd.read_csv(path)


@st.cache_resource
def load_prediction_model(path):

    return joblib.load(path)


# ==================================================
# 5. HEADER
# ==================================================

st.markdown(
    '<div class="main-header">'
    'AI-Based Tool Wear Prediction'
    '</div>',
    unsafe_allow_html=True
)

st.caption(
    "Random Forest regression for estimating milling "
    "tool wear from extracted machine sensor features."
)


# ==================================================
# 6. CHECK FILES
# ==================================================

if not DATA_PATH.exists():

    st.error("NASA dataset not found.")
    st.stop()

if not FEATURE_PATH.exists():

    st.error("Feature dataset not found.")
    st.stop()

if not MODEL_PATH.exists():

    st.error("Trained AI model not found.")
    st.stop()


# ==================================================
# 7. LOAD MODEL AND DATA
# ==================================================

try:

    metadata = load_metadata(str(DATA_PATH))

    feature_table = load_feature_table(
        str(FEATURE_PATH)
    )

    model_bundle = load_prediction_model(
        str(MODEL_PATH)
    )

except Exception as error:

    st.error(f"Could not load AI resources: {error}")
    st.stop()


# ==================================================
# 8. MODEL OVERVIEW
# ==================================================

st.markdown(
    '<div class="section-heading">Model Overview</div>',
    unsafe_allow_html=True
)

render_kpi_cards([
    {
        "label": "Algorithm",
        "value": "Random Forest",
        "icon": "◈",
        "accent": "#2563EB",
        "icon_bg": "#EFF6FF",
    },
    {
        "label": "Input Features",
        "value": len(model_bundle["feature_columns"]),
        "icon": "⌁",
        "accent": "#0891B2",
        "icon_bg": "#ECFEFF",
    },
    {
        "label": "Training Experiments",
        "value": model_bundle.get(
            "training_experiments", "N/A"
        ),
        "icon": "▦",
        "accent": "#6366B9",
        "icon_bg": "#EEF2FF",
    },
])

st.html(
    """
    <div class="info-banner">
        <div class="info-banner-icon">ⓘ</div>
        <div class="info-banner-text">
            <strong>Model purpose:</strong>
            The model estimates tool wear (VB).
            It does not predict remaining useful life (RUL)
            or guarantee machine-failure detection.
        </div>
    </div>
    """
)

st.divider()


# ==================================================
# 9. EXPERIMENT SELECTION
# ==================================================

st.markdown(
    '<div class="section-heading">Prediction Results</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="section-description">'
    'Select an experiment to view its estimated and measured tool wear.'
    '</div>',
    unsafe_allow_html=True
)

selected_index = st.selectbox(
    "Select Experiment",
    range(len(metadata)),
    format_func=lambda i: (
        f"Experiment {i + 1} | "
        f"Case {int(metadata.iloc[i]['Case'])} | "
        f"Run {int(metadata.iloc[i]['Run'])}"
    )
)

selected = metadata.iloc[selected_index]

experiment_number = selected_index + 1


# ==================================================
# 10. GENERATE PREDICTION
# ==================================================

experiment_features = feature_table[
    feature_table["experiment"] == experiment_number
]

if experiment_features.empty:

    st.warning(
        "No extracted sensor features are available "
        "for this experiment."
    )

    st.stop()


feature_columns = model_bundle["feature_columns"]

missing_columns = [
    column
    for column in feature_columns
    if column not in experiment_features.columns
]

if missing_columns:

    st.error(
        "Required model features are missing from the dataset."
    )

    st.stop()


X_selected = experiment_features[
    feature_columns
].replace(
    [np.inf, -np.inf],
    np.nan
)

X_values = X_selected.to_numpy(dtype=float)

valid_data = (
    np.isfinite(X_values).all()
    and (np.abs(X_values) <= 1e10).all()
)

if not valid_data:

    st.warning(
        "Prediction unavailable because this experiment "
        "contains invalid or excessively large sensor features."
    )

    if experiment_number == 18:

        st.info(
            "Experiment 18 was excluded from model training "
            "because of extreme sensor values."
        )

    st.stop()


predicted_vb = model_bundle["model"].predict(
    X_selected
)[0]

actual_vb = selected["Tool Wear (VB)"]


# ==================================================
# 11. PREDICTION RESULT CARDS
# ==================================================

if pd.notna(actual_vb):

    difference = abs(predicted_vb - actual_vb)

    render_kpi_cards([
        {
            "label": "AI Estimated Tool Wear",
            "value": f"{predicted_vb:.4f}",
            "icon": "◈",
            "accent": "#2563EB",
            "icon_bg": "#EFF6FF",
        },
        {
            "label": "Measured Tool Wear",
            "value": f"{actual_vb:.4f}",
            "icon": "✓",
            "accent": "#64748B",
            "icon_bg": "#F1F5F9",
        },
        {
            "label": "Absolute Difference",
            "value": f"{difference:.4f}",
            "icon": "↔",
            "accent": "#0891B2",
            "icon_bg": "#ECFEFF",
        },
    ])

else:

    render_kpi_cards([
        {
            "label": "AI Estimated Tool Wear",
            "value": f"{predicted_vb:.4f}",
            "icon": "◈",
            "accent": "#2563EB",
            "icon_bg": "#EFF6FF",
        },
        {
            "label": "Measured Tool Wear",
            "value": "Not available",
            "icon": "—",
            "accent": "#64748B",
            "icon_bg": "#F1F5F9",
        },
        {
            "label": "Prediction Difference",
            "value": "Not available",
            "icon": "—",
            "accent": "#0891B2",
            "icon_bg": "#ECFEFF",
        },
    ])


# ==================================================
# 12. MEASURED VS ESTIMATED CHART
# ==================================================

if pd.notna(actual_vb):

    comparison_fig = go.Figure()

    comparison_fig.add_trace(
        go.Bar(
            x=["Measured VB"],
            y=[actual_vb],
            width=0.42,
            marker=dict(
                color="#94A3B8",
                line=dict(
                    color="#64748B",
                    width=1
                )
            ),
            text=[f"{actual_vb:.4f}"],
            textposition="outside",
            cliponaxis=False,
            name="Measured VB",
            hovertemplate=(
                "Measured VB: %{y:.4f}"
                "<extra></extra>"
            )
        )
    )

    comparison_fig.add_trace(
        go.Bar(
            x=["AI Estimated VB"],
            y=[predicted_vb],
            width=0.42,
            marker=dict(
                color="#2563EB",
                line=dict(
                    color="#1D4ED8",
                    width=1
                )
            ),
            text=[f"{predicted_vb:.4f}"],
            textposition="outside",
            cliponaxis=False,
            name="AI Estimated VB",
            hovertemplate=(
                "AI Estimated VB: %{y:.4f}"
                "<extra></extra>"
            )
        )
    )

    # Calculate suitable chart headroom automatically
    chart_values = [
        float(actual_vb),
        float(predicted_vb)
    ]

    max_value = max(chart_values)
    min_value = min(chart_values)

    value_span = max(
        max_value - min_value,
        abs(max_value) * 0.5,
        0.01
    )

    padding = value_span * 0.30

    lower_limit = min(0, min_value - padding)
    upper_limit = max(0, max_value + padding)

    comparison_fig.update_layout(
        title=dict(
            text="Measured vs AI Estimated Tool Wear",
            x=0.02,
            xanchor="left",
            font=dict(
                size=17,
                color="#172B43"
            )
        ),
        yaxis=dict(
            title="Tool Wear (VB)",
            range=[lower_limit, upper_limit],
            gridcolor="#EDF1F5",
            zerolinecolor="#94A3B8",
            tickformat=".4f"
        ),
        xaxis=dict(
            title="",
            tickfont=dict(
                size=12,
                color="#334155"
            )
        ),
        height=440,
        showlegend=False,
        bargap=0.55,
        template="plotly_white",
        margin=dict(
            l=70,
            r=35,
            t=90,
            b=65
        ),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font=dict(
            family="Arial, sans-serif",
            color="#334155"
        )
    )

    with st.container(border=True):

        st.plotly_chart(
            comparison_fig,
            use_container_width=True,
            config={"displaylogo": False}
        )

else:

    st.info(
        "This experiment has no measured wear value. "
        "Only the AI estimate is available."
    )


st.divider()


# ==================================================
# 13. MODEL VALIDATION PERFORMANCE
# ==================================================

st.markdown(
    '<div class="section-heading">'
    'Model Validation Performance'
    '</div>',
    unsafe_allow_html=True
)

metrics = model_bundle.get("metrics", {})

mae = metrics.get("mae", float("nan"))
rmse = metrics.get("rmse", float("nan"))
r2 = metrics.get("r2", float("nan"))

render_kpi_cards([
    {
        "label": "Validation MAE",
        "value": f"{mae:.4f}",
        "icon": "↔",
        "accent": "#0D9488",
        "icon_bg": "#F0FDFA",
    },
    {
        "label": "Validation RMSE",
        "value": f"{rmse:.4f}",
        "icon": "⌁",
        "accent": "#6366B9",
        "icon_bg": "#EEF2FF",
    },
    {
        "label": "Validation R²",
        "value": f"{r2:.4f}",
        "icon": "▥",
        "accent": "#0891B2",
        "icon_bg": "#ECFEFF",
    },
])

st.markdown(
    """
    **Validation method:** GroupKFold by experimental case,
    using five folds.
    """
)

with st.expander("View Training Information"):

    st.write(
        "Training experiments:",
        model_bundle.get("training_experiments", "N/A")
    )

    st.write(
        "Excluded experiments:",
        model_bundle.get("excluded_experiments", [])
    )

    st.write(
        "Model algorithm: Random Forest Regression"
    )

    st.write(
        "Input: 60 features extracted from six sensor channels."
    )


# ==================================================
# 14. MODEL LIMITATIONS
# ==================================================

st.divider()

st.markdown(
    '<div class="section-heading">Model Limitations</div>',
    unsafe_allow_html=True
)

st.html(
    """
    <div class="limitation-card">

        <div class="limitation-title">
            ⚠ Important interpretation notes
        </div>

        <ul class="limitation-list">
            <li>The model estimates measured tool wear (VB).</li>
            <li>It does not estimate remaining useful life (RUL).</li>
            <li>It does not independently confirm machine faults.</li>
            <li>
                The displayed comparison for a labelled experiment
                is an in-sample comparison, not an independent
                test prediction.
            </li>
            <li>
                Experimental performance should not be interpreted
                as guaranteed industrial performance.
            </li>
        </ul>

    </div>
    """
)

st.caption(
    "Model evaluation uses grouped cross-validation by experimental case. "
    "Validation metrics describe the model evaluation, not the accuracy "
    "of every individual displayed prediction."
)
