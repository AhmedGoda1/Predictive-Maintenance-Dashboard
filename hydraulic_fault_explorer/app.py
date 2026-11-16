from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Hydraulic Fault Explorer", layout="wide")

data_dir = Path(__file__).parent / "data"
profile = pd.read_csv(data_dir / "profile.txt", sep="\t", header=None)
flow = pd.read_csv(data_dir / "FS1.txt", sep="\t", header=None)

healthy = (
    profile[0].eq(100)
    & profile[1].eq(100)
    & profile[2].eq(0)
    & profile[3].eq(130)
    & profile[4].eq(0)
)
reference = flow.loc[healthy].median()

title, picker = st.columns([3, 1])
title.title("Hydraulic Fault Explorer")
cycle = picker.number_input(
    "Test cycle", min_value=1, max_value=len(profile),
    value=int(profile.index[profile[2].eq(2)][0]) + 1,
)
row = cycle - 1

headline, condition = {
    0: ("No pump leak recorded", "No leakage"),
    1: ("Check the pump", "Weak internal leakage"),
    2: ("Inspect the pump first", "Severe internal leakage"),
}[profile.at[row, 2]]

st.subheader(headline)
st.caption(f"Recorded test condition · {condition}")

chart = pd.DataFrame({
    "Selected cycle": flow.iloc[row].to_numpy(),
    "Healthy reference": reference.to_numpy(),
})
chart.index = chart.index / 10
st.line_chart(chart, x_label="Seconds", y_label="Flow (L/min)", height=270)