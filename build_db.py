"""Builds maintenance.db from the dataset: ingest readings, then run the analysis.

Usage: python build_db.py
"""
import db_manager
import health
import ingest


def build(db_path=None) -> dict:
    n = ingest.ingest(db_path)
    result = health.analyze(ingest.MACHINE_ID, db_path)
    result["readings_ingested"] = n
    return result


if __name__ == "__main__":
    for key, value in build().items():
        print(f"{key}: {value:,.1f}" if isinstance(value, float) else f"{key}: {value}")
    print(f"Database written to {db_manager.DB_NAME}")
