
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat
from scipy.stats import kurtosis, skew


DATA_PATH = (
    Path(__file__).resolve().parents[1]
    / "Data_Milling_Machine"
    / "mill.mat"
)

SENSORS = [
    "smcAC",
    "smcDC",
    "vib_table",
    "vib_spindle",
    "AE_table",
    "AE_spindle",
]


def extract_signal_features(signal):
    """Calculate statistical features from one sensor signal."""

    x = np.asarray(signal, dtype=float).flatten()
    x = x[np.isfinite(x)]

    if x.size == 0:
        return {
            "mean": np.nan,
            "std": np.nan,
            "rms": np.nan,
            "peak_to_peak": np.nan,
            "max": np.nan,
            "min": np.nan,
            "crest_factor": np.nan,
            "kurtosis": np.nan,
            "skewness": np.nan,
            "energy": np.nan,
        }

    rms = np.sqrt(np.mean(x ** 2))
    peak = np.max(np.abs(x))

    return {
        "mean": np.mean(x),
        "std": np.std(x),
        "rms": rms,
        "peak_to_peak": np.ptp(x),
        "max": np.max(x),
        "min": np.min(x),
        "crest_factor": peak / rms if rms > 0 else np.nan,
        "kurtosis": kurtosis(x, fisher=False),
        "skewness": skew(x),
        "energy": np.sum(x ** 2),
    }


def load_and_extract_features(data_path=DATA_PATH):
    """Load NASA milling data and create one feature row per experiment."""

    if not Path(data_path).exists():
        raise FileNotFoundError(f"Dataset not found: {data_path}")

    mat_data = loadmat(data_path)
    experiments = mat_data["mill"]

    rows = []

    for i in range(experiments.shape[1]):
        record = experiments[0, i]

        row = {
            "experiment": i + 1,
            "case": int(np.asarray(record["case"]).squeeze()),
            "run": int(np.asarray(record["run"]).squeeze()),
            "VB": float(np.asarray(record["VB"]).squeeze()),
            "time": float(np.asarray(record["time"]).squeeze()),
            "DOC": float(np.asarray(record["DOC"]).squeeze()),
            "feed": float(np.asarray(record["feed"]).squeeze()),
            "material": str(
                np.asarray(record["material"]).squeeze()
            ),
        }

        for sensor in SENSORS:
            signal = np.asarray(record[sensor]).squeeze()
            features = extract_signal_features(signal)

            for feature_name, value in features.items():
                row[f"{sensor}_{feature_name}"] = value

        rows.append(row)

    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = load_and_extract_features()

    print("\nFEATURE ENGINEERING RESULTS")
    print("-" * 40)
    print("Total experiments:", len(df))
    print("Total columns:", len(df.columns))
    print("Valid VB labels:", df["VB"].notna().sum())
    print("Missing VB labels:", df["VB"].isna().sum())

    print("\nFeature table preview:")
    print(df.head())

    print("\nMissing values:")
    print(df.isna().sum()[df.isna().sum() > 0])

    output_path = (
        Path(__file__).resolve().parents[1]
        / "database"
        / "milling_features.csv"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    print("\nFeature table saved to:")
    print(output_path)
