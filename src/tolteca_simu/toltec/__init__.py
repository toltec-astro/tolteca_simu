"""The TolTEC instrument specialization for planning."""

from .coverage import CoverageMap, Footprint, get_coverage_map, get_footprint
from .info import TOLTEC_ARRAYS, ToltecArrayInfo, ToltecArrayName

__all__ = [
    "TOLTEC_ARRAYS",
    "CoverageMap",
    "Footprint",
    "ToltecArrayInfo",
    "ToltecArrayName",
    "get_coverage_map",
    "get_footprint",
]
