import os
from pathlib import Path

import pytest

# The calibration data store is a sibling checkout in the development location;
# TOLTECA_SIMU_CAL_DATA_PATH points elsewhere.
_CAL_DATA_PATH = Path(
    os.environ.get(
        "TOLTECA_SIMU_CAL_DATA_PATH",
        Path(__file__).resolve().parents[2] / "tolteca_cal_data",
    )
)


@pytest.fixture(scope="session")
def cal_data_path() -> Path:
    if not (_CAL_DATA_PATH / "manifest.json").exists():
        pytest.skip(f"No calibration data store at {_CAL_DATA_PATH}")
    return _CAL_DATA_PATH
