"""Brushed DC motor run-to-failure data.

"F.A.I.R. open dataset of brushed DC motor faults for testing of AI algorithms",
A. Reñones (CARTIF), https://zenodo.org/records/4314249, CC-BY-4.0.
One motor was monitored until it failed; the processing sheet has one row per raw recording.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from .base import Run

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
WORKBOOK = DATA_DIR / "open_DC_motor-processing_data.xlsx"
PHASE_MAP = DATA_DIR / "file_phases.csv"

ASSET_ID = "MTR_01"
TYPE_ID = "brushed_dc_motor"
SOURCE = "Zenodo 4314249"
FAILED_VOLTAGE = 1.5   # supply collapsing below this at the end of the run = motor stopped

COLUMN_MAP = {
    "speed_rpm": "speed_rpm", "Current": "current", "Voltage": "voltage",
    "temp_mot": "temp_motor", "temp_amb": "temp_ambient",
    "1x[Vibration]": "vib_1x", "5x[Vibration]": "vib_5x", "7x[Vibration]": "vib_7x",
    "0-4k_Hz[Vibration]": "vib_band_0_4k", "4k-8k_Hz[Vibration]": "vib_band_4_8k",
    "8k-16kHz[Vibration]": "vib_band_8_16k", "16k-26kHz[Vibration]": "vib_band_16_26k",
}


def load(workbook: Path = WORKBOOK, phase_map: Path = PHASE_MAP) -> Run:
    """Reads the workbook and returns the motor's single run."""
    raw = pd.read_excel(workbook)
    df = raw.rename(columns=COLUMN_MAP)[["File", "Date", *COLUMN_MAP.values()]]
    df["ts"] = pd.to_datetime(df.pop("Date"), format="%d/%m/%Y %H:%M:%S,%f")
    df = df.merge(pd.read_csv(phase_map), on="File", how="left")
    df = df.sort_values("ts").reset_index(drop=True)

    # Regime comes from the phase (folder name): the measured voltage reads ~0 when the motor stops.
    by_voltage = np.where(df["voltage"] > 4.0, 5.0, 3.0)
    df["voltage_regime"] = np.where(df["phase"].isna(), by_voltage,
                                    np.where(df["phase"].str.contains("5V", na=False), 5.0, 3.0))
    df["age"] = (df["ts"] - df["ts"].iloc[0]).dt.total_seconds()

    # The motor died at the end of the run: the supply collapses and stays down.
    low = (df["voltage"] < FAILED_VOLTAGE).to_numpy()
    n_failed = 0
    for flag in low[::-1]:
        if not flag:
            break
        n_failed += 1
    failure_age = float(df["age"].iloc[len(df) - n_failed]) if n_failed else None

    segments = (df.dropna(subset=["phase"]).groupby("phase", sort=False)["ts"]
                .agg(start_ts="min", end_ts="max").reset_index().rename(columns={"phase": "name"}))
    channels = ["ts", "age", "voltage_regime", *COLUMN_MAP.values()]
    return Run(
        asset_id=ASSET_ID, type_id=TYPE_ID, name="Brushed DC Motor (run-to-failure test)",
        series=df[channels], failure_age=failure_age, failure_observed=failure_age is not None,
        source=SOURCE, split="train", segments=segments,
        metadata={"location": "Test bench"},
    )
