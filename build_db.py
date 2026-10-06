"""Builds maintenance.db from the datasets: loads the assets, runs the analysis, stores the results.

Usage: python build_db.py [--no-fleet] [--retrain]
"""
import sys

from pdm import db, pipeline

if __name__ == "__main__":
    result = pipeline.build(fleet="--no-fleet" not in sys.argv, retrain="--retrain" in sys.argv)
    for part, info in result.items():
        print(f"{part}: {info}")
    print(f"Database written to {db.DB_NAME}")
