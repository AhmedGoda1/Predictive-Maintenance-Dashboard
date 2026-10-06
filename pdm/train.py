"""Trains and evaluates the learned RUL model on the NASA C-MAPSS subsets.

Protocol: fit on the train engines (group-aware cross-validation inside, so an engine is never
in both the fitting and the calibration folds), then predict the remaining life at the last
reading of every held-out test engine and compare with the true RUL from the benchmark.

Usage: python -m pdm.train [FD001 FD002 ...]     (default: all subsets whose data is available)
"""
import json
import sys
import time
from pathlib import Path

from . import rul
from .datasets import cmapss

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
METRICS_FILE = MODELS_DIR / "cmapss_metrics.json"
N_REGIMES = {"FD001": 1, "FD002": 6, "FD003": 1, "FD004": 6}   # operating conditions per subset (NASA readme)


def model_path(subset: str) -> Path:
    return MODELS_DIR / f"turbofan_{subset}.joblib"


def train_subset(subset: str, save: bool = True, **model_kwargs) -> dict:
    t0 = time.time()
    train, test = cmapss.load(subset, "train"), cmapss.load(subset, "test")
    model = rul.RulModel("turbofan_engine", n_regimes=N_REGIMES[subset], **model_kwargs).fit(train)
    result = {
        "subset": subset, "n_train_engines": len(train), "n_test_engines": len(test),
        "n_regimes": N_REGIMES[subset], "rul_cap": model.rul_cap,
        "cv": {"oof_rmse_capped": model.report.oof_rmse, "oof_mae_capped": model.report.oof_mae,
               "conformal_q": model.report.conformal_q},
        "test": rul.evaluate_last_reading(model, test),
        "baselines": rul.baseline_metrics(train, test, model.rul_cap),
        "seconds": round(time.time() - t0, 1),
    }
    if save:
        model.save(model_path(subset))
    return result


def main(subsets=None) -> dict:
    subsets = subsets or [s for s in cmapss.SUBSETS if cmapss.available(s)]
    results = json.loads(METRICS_FILE.read_text()) if METRICS_FILE.exists() else {}
    for s in subsets:
        print(f"training {s} ...", flush=True)
        results[s] = train_subset(s)
        t = results[s]["test"]
        print(f"  test RMSE {t['rmse']:.1f}  MAE {t['mae']:.1f}  NASA score {t['nasa_score']:.0f}  "
              f"coverage {t['coverage']:.2f}  ({results[s]['seconds']} s)", flush=True)
        MODELS_DIR.mkdir(exist_ok=True)
        METRICS_FILE.write_text(json.dumps(results, indent=2, sort_keys=True))
    return results


if __name__ == "__main__":
    main(sys.argv[1:] or None)
