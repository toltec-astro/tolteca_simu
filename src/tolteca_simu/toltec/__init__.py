"""The TolTEC instrument specialization for planning and simulation."""

from .coverage import (
    CoverageMap,
    Footprint,
    get_array_outline,
    get_coverage_map,
    get_footprint,
    place_on_sky,
)
from .detectors import DetectorPositions, get_detector_positions
from .info import TOLTEC_ARRAYS, TOLTEC_PLATE_SCALE, ToltecArrayInfo, ToltecArrayName

__all__ = [
    "TOLTEC_ARRAYS",
    "TOLTEC_PLATE_SCALE",
    "CoverageMap",
    "DetectorPositions",
    "Footprint",
    "ToltecArrayInfo",
    "ToltecArrayName",
    "get_array_outline",
    "get_coverage_map",
    "get_detector_positions",
    "get_footprint",
    "place_on_sky",
]
