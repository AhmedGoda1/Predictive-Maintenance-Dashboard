import os
import sys
from pathlib import Path

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from pdm.db import init_db, upsert_asset, insert_series
from pdm.datasets.battery import load_battery_data

def build_database():
    db_path = Path("maintenance.db")
    if db_path.exists():
        db_path.unlink()
        
    # Initialize schema and register all asset types (including battery)
    init_db(db_path, reset=True)

    # 1. Default Motor setup
    print("Adding default motor asset...")
    upsert_asset(
        asset_id="MTR_01", 
        type_id="brushed_dc_motor", 
        name="Brushed DC Motor Demo", 
        site="Lab", 
        source="motor_run.csv",
        db_path=db_path
    )

    # 2. Add NASA Batteries from Downloads if folder exists
    battery_dir = Path(r"C:\Users\agoda\Downloads\battery_fy08")
    battery_files = ["B0005.mat", "B0006.mat", "B0007.mat", "B0018.mat"]
    
    battery_count = 0
    if battery_dir.exists():
        for filename in battery_files:
            mat_path = battery_dir / filename
            if mat_path.exists():
                asset_id = filename.split(".")[0]
                print(f"Loading and inserting battery {asset_id}...")
                df = load_battery_data(mat_path)
                
                # Register battery asset in DB
                upsert_asset(
                    asset_id=asset_id,
                    type_id="battery",
                    name=f"NASA Battery {asset_id}",
                    site="Ames Research Center",
                    source=filename,
                    db_path=db_path
                )
                
                # Insert its cycle readings into the time-series tables
                insert_series(asset_id, df, db_path=db_path)
                battery_count += 1
    else:
        print("Battery folder not found in Downloads, skipping battery import.")

    print(f"Database successfully built with {battery_count} batteries added.")

if __name__ == "__main__":
    build_database()