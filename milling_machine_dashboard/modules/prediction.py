
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestRegressor
from sklearn.dummy import DummyRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


# --------------------------------------------------
# 1. File locations
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[1]

FEATURE_PATH = BASE_DIR / "database" / "milling_features.csv"
MODEL_PATH = BASE_DIR / "models" / "milling_wear_model.joblib"


# --------------------------------------------------
# 2. Load feature dataset
# --------------------------------------------------

print("\nMILLING MACHINE TOOL-WEAR PREDICTION")
print("=" * 50)

if not FEATURE_PATH.exists():
    raise FileNotFoundError(
        f"Feature dataset not found: {FEATURE_PATH}\n"
        "Run feature_engineering.py first."
    )

df = pd.read_csv(FEATURE_PATH)

print("Total experiments in dataset:", len(df))


# --------------------------------------------------
# 3. Select sensor features
# --------------------------------------------------

sensor_names = [
    "smcAC",
    "smcDC",
    "vib_table",
    "vib_spindle",
    "AE_table",
    "AE_spindle",
]

feature_columns = [
    column
    for column in df.columns
    if any(column.startswith(sensor + "_") for sensor in sensor_names)
]

if not feature_columns:
    raise ValueError("No sensor features were found in the dataset.")

print("Number of sensor features:", len(feature_columns))


# --------------------------------------------------
# 4. Keep experiments with measured tool wear
# --------------------------------------------------

labelled = df.dropna(subset=["VB"]).copy()

print("Experiments with measured tool wear:", len(labelled))


# --------------------------------------------------
# 5. Data quality screening
# --------------------------------------------------

X = labelled[feature_columns].replace(
    [np.inf, -np.inf], np.nan
)

# Exclude experiments containing corrupted or
# excessively large sensor feature values.

valid_mask = (
    np.isfinite(X).all(axis=1)
    & (X.abs() <= 1e10).all(axis=1)
)

excluded = labelled.loc[~valid_mask, "experiment"].tolist()

labelled = labelled.loc[valid_mask].copy()
X = X.loc[valid_mask]

y = labelled["VB"]
groups = labelled["case"]

print("Excluded experiments:", excluded)
print("Usable labelled experiments:", len(labelled))


# --------------------------------------------------
# 6. Check dataset before training
# --------------------------------------------------

if len(labelled) < 10:
    raise ValueError("Not enough valid experiments for model training.")

number_of_cases = groups.nunique()

if number_of_cases < 2:
    raise ValueError("Not enough different cases for grouped validation.")

n_splits = min(5, number_of_cases)

print("Number of different cases:", number_of_cases)
print("Cross-validation folds:", n_splits)


# --------------------------------------------------
# 7. Create Random Forest model
# --------------------------------------------------

random_forest = Pipeline([
    ("imputer", SimpleImputer(strategy="median")),

    ("model", RandomForestRegressor(
        n_estimators=150,
        max_depth=8,
        min_samples_leaf=2,
        max_features=0.8,
        random_state=42,
        n_jobs=-1
    ))
])


# --------------------------------------------------
# 8. Group-based cross-validation
# --------------------------------------------------

# Experiments from the same case are kept together
# to reduce data leakage between training and testing.

cv = GroupKFold(n_splits=n_splits)

print("\nEvaluating Random Forest model...")

rf_predictions = cross_val_predict(
    random_forest,
    X,
    y,
    cv=cv,
    groups=groups
)


# --------------------------------------------------
# 9. Baseline model comparison
# --------------------------------------------------

baseline = DummyRegressor(strategy="median")

baseline_predictions = cross_val_predict(
    baseline,
    X,
    y,
    cv=cv,
    groups=groups
)


# --------------------------------------------------
# 10. Calculate performance metrics
# --------------------------------------------------

rf_mae = mean_absolute_error(y, rf_predictions)

rf_rmse = np.sqrt(
    mean_squared_error(y, rf_predictions)
)

rf_r2 = r2_score(y, rf_predictions)


baseline_mae = mean_absolute_error(
    y, baseline_predictions
)

baseline_rmse = np.sqrt(
    mean_squared_error(y, baseline_predictions)
)

baseline_r2 = r2_score(
    y, baseline_predictions
)


# --------------------------------------------------
# 11. Display model results
# --------------------------------------------------

print("\nMODEL PERFORMANCE")
print("-" * 50)

print("\nRandom Forest:")
print(f"MAE  : {rf_mae:.4f}")
print(f"RMSE : {rf_rmse:.4f}")
print(f"R²   : {rf_r2:.4f}")

print("\nMedian Baseline:")
print(f"MAE  : {baseline_mae:.4f}")
print(f"RMSE : {baseline_rmse:.4f}")
print(f"R²   : {baseline_r2:.4f}")


print("\nMODEL COMPARISON")
print("-" * 50)

if rf_mae < baseline_mae:
    print("Random Forest has lower MAE than the baseline.")
else:
    print("Random Forest does not outperform the baseline in MAE.")

if rf_rmse < baseline_rmse:
    print("Random Forest has lower RMSE than the baseline.")
else:
    print("Random Forest does not outperform the baseline in RMSE.")


# --------------------------------------------------
# 12. Train final model using all usable labelled data
# --------------------------------------------------

print("\nTraining final Random Forest model...")

random_forest.fit(X, y)


# --------------------------------------------------
# 13. Save trained model
# --------------------------------------------------

MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

model_bundle = {
    "model": random_forest,
    "feature_columns": feature_columns,
    "target": "VB",
    "model_name": "Random Forest Regressor",
    "training_experiments": len(labelled),
    "excluded_experiments": excluded,
    "validation": "GroupKFold by case",
    "metrics": {
        "mae": float(rf_mae),
        "rmse": float(rf_rmse),
        "r2": float(rf_r2),
        "baseline_mae": float(baseline_mae),
        "baseline_rmse": float(baseline_rmse),
        "baseline_r2": float(baseline_r2),
    },
}

joblib.dump(model_bundle, MODEL_PATH)


# --------------------------------------------------
# 14. Completion
# --------------------------------------------------

print("\n" + "=" * 50)
print("MODEL TRAINING COMPLETED")
print("=" * 50)

print("Saved model to:")
print(MODEL_PATH)

print("\nThe model predicts measured tool wear (VB).")
print("It does not directly predict remaining useful life.")
