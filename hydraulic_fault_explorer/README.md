# Hydraulic Fault Explorer

A standalone dashboard for exploring pump leakage in a hydraulic test rig. Select a recorded test cycle to see the pump’s recorded condition and compare its 60-second flow trace with a healthy reference.

**Access** — Run the app locally using the steps below. The Explorer requires no username or password.

## Architecture

```text
FS1.txt       ── flow readings ─┐
                               ├── Streamlit dashboard
profile.txt   ── test labels ────┘
```

The app matches the two files by row, with one row per test cycle. It builds the healthy reference by taking the median flow at each time point across stable cycles with all four components in their nominal condition.

## Run it

1. Download and extract the [UCI Condition Monitoring of Hydraulic Systems dataset](https://archive.ics.uci.edu/dataset/447).
2. Create `hydraulic_fault_explorer/data/` and place `FS1.txt` and `profile.txt` inside it.
3. From the repository root, install the dependencies and start the app:

   ```powershell
   python -m pip install -r hydraulic_fault_explorer/requirements.txt
   python -m streamlit run hydraulic_fault_explorer/app.py
   ```

4. Open the **Local URL** printed in the terminal.

## Dashboard

Use **Test cycle** to change the displayed cycle. The headline summarizes the recorded pump condition, and the chart compares the selected cycle’s flow in L/min with the healthy reference.

| Test cycle | Recorded condition | Dashboard headline |
| --- | --- | --- |
| 1 | No leakage | No pump leak recorded |
| 220 | Severe internal leakage | Inspect the pump first |

## Dataset and scope

The UCI dataset contains 2,205 one-minute cycles from a hydraulic test rig. `FS1.txt` contains flow readings sampled at 10 Hz. The third column of `profile.txt` records pump leakage as none, weak, or severe.
Dataset: Helwig, N., Pignanelli, E., & Schütze, A. (2015).
[Condition monitoring of hydraulic systems](https://doi.org/10.24432/C5CW21),
UCI Machine Learning Repository. The included `FS1.txt` and `profile.txt`
files are distributed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

The app displays those recorded labels. Use the chart to explore differences in flow between cycles.
