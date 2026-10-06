import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dashboard"))      # the dashboard modules are imported by name (data_source, utils, ...)


@pytest.fixture(scope="session")
def built_db(tmp_path_factory):
    """A database built once from the datasets and shared by the pipeline and dashboard tests."""
    from pdm import pipeline
    path = tmp_path_factory.mktemp("db") / "maintenance.db"
    pipeline.build(path)
    return path
