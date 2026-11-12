"""NASA C-MAPSS turbofan engine degradation simulation (run-to-failure fleets).

A. Saxena, K. Goebel, D. Simon, N. Eklund, "Damage Propagation Modeling for Aircraft Engine
Run-to-Failure Simulation", PHM 2008. NASA Ames Prognostics Data Repository (public domain).

Four subsets with 100-260 engines each:
  FD001 one condition / one fault mode   FD002 six conditions / one fault mode
  FD003 one condition / two fault modes  FD004 six conditions / two fault modes
Train engines run to failure; test engines stop before failure and come with their true RUL.
One cycle is mapped to one hour on a synthetic timeline.
"""
import gzip
import io
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

from .base import Run

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "cmapss"
SUBSETS = ("FD001", "FD002", "FD003", "FD004")
TYPE_ID = "turbofan_engine"
SOURCE = "NASA C-MAPSS"
URL = ("https://phm-datasets.s3.amazonaws.com/NASA/"
       "6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip")
COLUMNS = ["unit", "cycle", "op1", "op2", "op3"] + [f"s{i}" for i in range(1, 22)]
T0 = pd.Timestamp("2020-01-01")


def _path(kind: str, subset: str, data_dir: Path) -> Path:
    name = f"RUL_{subset}.txt" if kind == "RUL" else f"{kind}_{subset}.txt.gz"
    return Path(data_dir) / name


def available(subset: str, data_dir: Path = DATA_DIR) -> bool:
    return all(_path(k, subset, data_dir).exists() for k in ("train", "test", "RUL"))


def fetch(data_dir: Path = DATA_DIR, subsets=SUBSETS) -> None:
    """Downloads the dataset from NASA and stores each subset's files under data_dir."""
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(URL, timeout=300) as resp:
        outer = zipfile.ZipFile(io.BytesIO(resp.read()))
    inner_name = next(n for n in outer.namelist() if n.endswith("CMAPSSData.zip"))
    inner = zipfile.ZipFile(io.BytesIO(outer.read(inner_name)))
    for subset in subsets:
        for kind in ("train", "test"):
            with gzip.open(_path(kind, subset, data_dir), "wb") as f:
                f.write(inner.read(f"{kind}_{subset}.txt"))
        _path("RUL", subset, data_dir).write_bytes(inner.read(f"RUL_{subset}.txt"))


def read_raw(subset: str, split: str, data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """The raw table of a split (train / test) with named columns."""
    return pd.read_csv(_path(split, subset, data_dir), sep=r"\s+", header=None, names=COLUMNS)


def load(subset: str = "FD001", split: str = "train", data_dir: Path = DATA_DIR, units=None) -> list:
    """Engines of one subset/split as Run objects (optionally only the given unit numbers)."""
    if subset not in SUBSETS:
        raise ValueError(f"subset must be one of {SUBSETS}")
    if split not in ("train", "test"):
        raise ValueError("split must be 'train' or 'test'")
    if not available(subset, data_dir):
        raise FileNotFoundError(
            f"C-MAPSS {subset} not found in {data_dir}. Run: python scripts/fetch_cmapss.py")
    raw = read_raw(subset, split, data_dir)
    final_rul = pd.read_csv(_path("RUL", subset, data_dir), header=None)[0].to_numpy() if split == "test" else None

    runs = []
    for unit, g in raw.groupby("unit", sort=True):
        if units is not None and unit not in units:
            continue
        g = g.sort_values("cycle")
        series = g.drop(columns=["unit"]).rename(columns={"cycle": "age"}).reset_index(drop=True)
        series["age"] = series["age"].astype(float)
        series.insert(0, "ts", T0 + pd.to_timedelta(series["age"], unit="h"))
        last = float(series["age"].iloc[-1])
        if split == "train":                      # run to failure: the last cycle is the failure
            failure_age, observed = last, True
        else:                                     # censored: true remaining life is given separately
            failure_age, observed = last + float(final_rul[unit - 1]), False
        runs.append(Run(
            asset_id=f"{subset}-{split}-{int(unit):03d}", type_id=TYPE_ID,
            name=f"Engine {int(unit):03d} ({subset} {split})", series=series,
            failure_age=failure_age, failure_observed=observed, source=f"{SOURCE} {subset}",
            split=split, metadata={"subset": subset, "unit": int(unit)},
        ))
    return runs
