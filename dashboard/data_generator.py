import pandas as pd
import numpy as np

def get_asset_metadata():
    """Returns static metadata for assets in the fleet."""
    data = [
        {"asset_id": "PUMP-101", "name": "Main Coolant Pump", "location": "Facility A - Bay 1", "type": "Centrifugal Pump"},
        {"asset_id": "TURB-202", "name": "Power Turbine B", "location": "Facility A - Bay 3", "type": "Gas Turbine"},
        {"asset_id": "COMP-303", "name": "Air Compressor 3", "location": "Facility B - Bay 2", "type": "Rotary Screw"},
        {"asset_id": "GEN-404", "name": "Backup Generator", "location": "Facility B - Bay 4", "type": "Diesel Engine"},
    ]
    return pd.DataFrame(data)

def generate_telemetry_data(num_hours=48):
    """Generates synthetic hourly sensor telemetry for all assets."""
    np.random.seed(42)
    assets = ["PUMP-101", "TURB-202", "COMP-303", "GEN-404"]
    records = []

    now = pd.Timestamp.now().floor("h")

    for asset_id in assets:
        base_temp = 65.0 if asset_id != "TURB-202" else 180.0
        base_vib = 2.5
        base_pres = 40.0

        for h in range(num_hours):
            timestamp = now - pd.Timedelta(hours=(num_hours - h))
            
            # Simulate degrading health/anomaly trend on PUMP-101 over time
            degradation = (h / num_hours) * 15.0 if asset_id == "PUMP-101" else 0.0

            temp = base_temp + degradation + np.random.normal(0, 1.2)
            vib = base_vib + (degradation * 0.2) + np.random.normal(0, 0.15)
            pres = base_pres - (degradation * 0.5) + np.random.normal(0, 0.8)

            records.append({
                "timestamp": timestamp,
                "asset_id": asset_id,
                "temperature_c": round(temp, 2),
                "vibration_mm_s": round(max(0, vib), 2),
                "pressure_psi": round(max(0, pres), 2)
            })

    return pd.DataFrame(records)

def generate_ml_predictions():
    """Generates mock ML output model predictions (RUL & Failure Probability)."""
    predictions = [
        {"asset_id": "PUMP-101", "health_score": 58, "rul_days": 12, "failure_prob": 0.78, "status": "Critical"},
        {"asset_id": "TURB-202", "health_score": 92, "rul_days": 145, "failure_prob": 0.08, "status": "Healthy"},
        {"asset_id": "COMP-303", "health_score": 81, "rul_days": 85, "failure_prob": 0.19, "status": "Healthy"},
        {"asset_id": "GEN-404", "health_score": 71, "rul_days": 38, "failure_prob": 0.35, "status": "Warning"},
    ]
    return pd.DataFrame(predictions)