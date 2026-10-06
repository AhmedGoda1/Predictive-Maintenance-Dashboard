"""Loads the processed brushed-DC-motor dataset into the SQLite database.

Dataset: "F.A.I.R. open dataset of brushed DC motor faults for testing of AI
algorithms", https://zenodo.org/records/4314249 (CC-BY-4.0).
The workbook has one row per raw HDF5 recording of a single motor that was
run until it failed.
"""
from pathlib import Path

import numpy as np
import pandas as pd

import db_manager

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
WORKBOOK = DATA_DIR / "open_DC_motor-processing_data.xlsx"
PHASE_MAP = DATA_DIR / "file_phases.csv"

MACHINE_ID = "MTR_01"
OVERSTRESS_VOLTAGE = 4.0   # supply above this is the 5 V overstress regime
FAILED_VOLTAGE = 1.5       # supply collapsing below this at the end of the run = motor stopped

COLUMN_MAP = {
    "File": "source_file",
    "speed_rpm": "speed_rpm",
    "Current": "current",
    "Voltage": "voltage",
    "temp_mot": "temp_motor",
    "temp_amb": "temp_ambient",
    "1x[Vibration]": "vib_1x",
    "5x[Vibration]": "vib_5x",
    "7x[Vibration]": "vib_7x",
    "0-4k_Hz[Vibration]": "vib_band_0_4k",
    "4k-8k_Hz[Vibration]": "vib_band_4_8k",
    "8k-16kHz[Vibration]": "vib_band_8_16k",
    "16k-26kHz[Vibration]": "vib_band_16_26k",
}


def load_dataset(workbook: Path = WORKBOOK, phase_map: Path = PHASE_MAP) -> pd.DataFrame:
    """Reads and cleans the workbook; adds phase, regime, failure flag and true RUL."""
    raw = pd.read_excel(workbook)
    df = raw.rename(columns=COLUMN_MAP)[["Date", *COLUMN_MAP.values()]]
    df["timestamp"] = pd.to_datetime(df.pop("Date"), format="%d/%m/%Y %H:%M:%S,%f")
    df = df.merge(pd.read_csv(phase_map).rename(columns={"File": "source_file"}),
                  on="source_file", how="left")
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["machine_id"] = MACHINE_ID

    # The motor died at the end of the run: voltage collapses and stays down.
    low = (df["voltage"] < FAILED_VOLTAGE).to_numpy()
    failed = np.zeros(len(df), dtype=bool)
    for i in range(len(df) - 1, -1, -1):
        if not low[i]:
            break
        failed[i] = True
    df["is_failed"] = failed.astype(int)

    # Supply regime; rows after failure inherit the last known regime.
    df["regime"] = np.where(df["voltage"] > OVERSTRESS_VOLTAGE, "5V", "3V")
    df.loc[failed, "regime"] = df.loc[~failed, "regime"].iloc[-1]

    if failed.any():
        failure_time = df.loc[failed, "timestamp"].iloc[0]
        df["rul_true_s"] = (failure_time - df["timestamp"]).dt.total_seconds().clip(lower=0)
    else:
        df["rul_true_s"] = np.nan  # no failure observed in this file
    return df


def ingest(db_path=None, workbook: Path = WORKBOOK, reset: bool = True) -> int:
    """Creates the database and fills machines + sensor_readings. Returns the row count."""
    db_manager.init_db(db_path, reset=reset)
    db_manager.insert_machine(
        MACHINE_ID, "Brushed DC Motor (run-to-failure test)", "Brushed DC Motor", "Test bench",
        db_path=db_path,
    )
    return db_manager.insert_readings_bulk(load_dataset(workbook), db_path=db_path)


if __name__ == "__main__":
    print(f"Ingested {ingest()} readings into {db_manager.DB_NAME}")
