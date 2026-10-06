"""Common in-memory format every dataset adapter produces."""
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from .. import db


@dataclass
class Run:
    """The recorded life of one asset.

    series: wide frame with ts, age and one column per channel (age in the asset type's age unit).
    failure_age: age at which the asset failed, or None when it is unknown.
    failure_observed: True when the failure is inside the recorded data, False when the failure
        time is only known from a label that lies beyond the last reading (right-censored run).
    """
    asset_id: str
    type_id: str
    name: str
    series: pd.DataFrame
    failure_age: Optional[float] = None
    failure_observed: bool = True
    source: str = ""
    split: str = "train"
    segments: Optional[pd.DataFrame] = None
    metadata: dict = field(default_factory=dict)

    @property
    def last_age(self) -> float:
        return float(self.series["age"].iloc[-1])

    def rul_true(self) -> Optional[np.ndarray]:
        """Ground-truth remaining life at every reading, or None when the failure time is unknown."""
        if self.failure_age is None:
            return None
        return np.clip(self.failure_age - self.series["age"].to_numpy(), 0, None)


def store(run: Run, db_path=None) -> int:
    """Writes a run (asset, readings, failure, segments) to the database."""
    db.upsert_asset(run.asset_id, run.type_id, run.name, source=run.source,
                    metadata={**run.metadata, "recorded": True, "split": run.split}, db_path=db_path)
    n = db.insert_series(run.asset_id, run.series, db_path)
    if run.failure_age is not None:
        ages = run.series["age"].to_numpy()
        ts = run.series["ts"]
        if run.failure_age <= ages[-1]:
            fail_ts = ts.iloc[int(np.searchsorted(ages, run.failure_age))]
        else:  # failure lies after the last reading: extrapolate the timeline
            step = (ts.iloc[-1] - ts.iloc[-2]) / max(ages[-1] - ages[-2], 1e-9) if len(ts) > 1 else pd.Timedelta(0)
            fail_ts = ts.iloc[-1] + step * (run.failure_age - ages[-1])
        db.set_failure(run.asset_id, fail_ts, run.failure_age, observed=run.failure_observed, db_path=db_path)
    if run.segments is not None and len(run.segments):
        db.set_segments(run.asset_id, run.segments, db_path)
    return n
