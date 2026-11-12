"""Downloads the NASA C-MAPSS dataset into data/cmapss/ (all four subsets).

Usage: python scripts/fetch_cmapss.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pdm.datasets import cmapss  # noqa: E402

if __name__ == "__main__":
    cmapss.fetch()
    for s in cmapss.SUBSETS:
        print(s, "ok" if cmapss.available(s) else "MISSING")
