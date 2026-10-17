"""Project time of a TolTEC observation, including overheads.

Follows the v1 planner's use of ``OverheadCalculation``: pointings at the start,
every hour and the end of each night, a tune before each science observation,
and the raster turnarounds as science overhead.
"""

from dataclasses import dataclass

import astropy.units as u
import numpy as np

__all__ = ["TimeCost", "get_time_cost"]

SCIENCE_TIME_PER_NIGHT = 4.0 << u.h
"""Assumed science time per observing night."""
# Tune (30 s), pointing observation (60 s), and a slew of up to 20 s.
_POINTING_TIME = 110 << u.s
_TUNE_TIME = 30 << u.s
_SCIENCE_OBS_TIME = 1 << u.h


@dataclass(frozen=True)
class TimeCost:
    """Project time of an observation.

    Attributes
    ----------
    science_time : astropy.units.Quantity
        Time on the mapping pattern for all passes.
    science_time_per_night : astropy.units.Quantity
        Assumed science time per night.
    n_nights : int
        Nights needed.
    science_overhead : astropy.units.Quantity
        Part of the science time spent off target (raster turnarounds).
    n_pointings : int
        Pointing observations.
    pointing_time : astropy.units.Quantity
        Time of pointings and tunes.
    total_time : astropy.units.Quantity
        Science time plus pointings and tunes.
    overhead_time : astropy.units.Quantity
        Science overhead plus pointings and tunes.
    """

    science_time: u.Quantity
    science_time_per_night: u.Quantity
    n_nights: int
    science_overhead: u.Quantity
    n_pointings: int
    pointing_time: u.Quantity
    total_time: u.Quantity
    overhead_time: u.Quantity

    @property
    def overhead_fraction(self) -> float:
        """Overhead as a fraction of the total time."""
        return float((self.overhead_time / self.total_time).to_value(u.one))


def get_time_cost(n_passes: int, t_exp: u.Quantity, t_exp_eff: u.Quantity) -> TimeCost:
    """Return the project time for passes of a mapping pattern.

    Parameters
    ----------
    n_passes : int
        Passes of the pattern.
    t_exp : astropy.units.Quantity
        Time per pass.
    t_exp_eff : astropy.units.Quantity
        On-target time per pass.

    Returns
    -------
    TimeCost
        Science, overhead, and total times.
    """
    science_time = (n_passes * t_exp).to(u.h)
    n_nights = int(np.ceil((science_time / SCIENCE_TIME_PER_NIGHT).to_value(u.one)))
    science_s = science_time.to_value(u.s)
    n_science_obs = np.ceil(science_s / _SCIENCE_OBS_TIME.to_value(u.s))
    n_pointings = n_science_obs + 1 + n_nights
    pointing_s = n_pointings * _POINTING_TIME.to_value(
        u.s
    ) + n_science_obs * _TUNE_TIME.to_value(u.s)
    overhead_fraction = (1 - t_exp_eff / t_exp).to_value(u.one)
    science_overhead_s = overhead_fraction * science_s
    return TimeCost(
        science_time=science_time,
        science_time_per_night=SCIENCE_TIME_PER_NIGHT,
        n_nights=n_nights,
        science_overhead=(science_overhead_s << u.s).to(u.h),
        n_pointings=int(n_pointings),
        pointing_time=(pointing_s << u.s).to(u.h),
        total_time=((science_s + pointing_s) << u.s).to(u.h),
        overhead_time=((science_overhead_s + pointing_s) << u.s).to(u.h),
    )
