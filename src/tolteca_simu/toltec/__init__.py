"""The TolTEC instrument specialization for planning and simulation."""

from .atmosphere import AtmospherePower, get_matched_pwv
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
from .signals import (
    DetectorLoading,
    KidsSignals,
    get_detector_loading,
    get_kids_signals,
    realize_power_noise,
)

__all__ = [
    "TOLTEC_ARRAYS",
    "TOLTEC_PLATE_SCALE",
    "AtmospherePower",
    "CoverageMap",
    "DetectorLoading",
    "DetectorPositions",
    "Footprint",
    "KidsSignals",
    "ToltecArrayInfo",
    "ToltecArrayName",
    "get_array_outline",
    "get_coverage_map",
    "get_detector_loading",
    "get_detector_positions",
    "get_footprint",
    "get_kids_signals",
    "get_matched_pwv",
    "place_on_sky",
    "realize_power_noise",
]
