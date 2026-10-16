"""Target elevation over the observing day."""

from dataclasses import dataclass

import astropy.units as u
import numpy as np
from astroplan import Observer
from astropy.coordinates import SkyCoord
from astropy.time import Time

__all__ = ["TargetVisibility", "get_target_visibility"]


@dataclass(frozen=True)
class TargetVisibility:
    """Target altitude over the UT day of an observation.

    Attributes
    ----------
    time : astropy.time.Time
        One sample per minute, from 00:00 UT of the observation day through the
        next 00:00 UT (1441 samples).
    alt : astropy.units.Quantity
        Target altitude at each sample.
    sun_rise_time : astropy.time.Time
        First sunrise after the day starts.
    sun_set_time : astropy.time.Time
        First sunset after the day starts.
    t0 : astropy.time.Time
        The observation start time.
    altaz_t0 : astropy.coordinates.SkyCoord
        Target azimuth and altitude at the start time.
    is_night_t0 : bool
        Whether the Sun is below the horizon at the start time.
    """

    time: Time
    alt: u.Quantity
    sun_rise_time: Time
    sun_set_time: Time
    t0: Time
    altaz_t0: SkyCoord
    is_night_t0: bool


def get_target_visibility(
    target: SkyCoord, t0: Time, observer: Observer
) -> TargetVisibility:
    """Compute the target altitude over the UT day containing a start time.

    Parameters
    ----------
    target : astropy.coordinates.SkyCoord
        The target coordinate.
    t0 : astropy.time.Time
        The observation start time; its UT day sets the time grid.
    observer : astroplan.Observer
        The observing site.

    Returns
    -------
    TargetVisibility
        Altitudes on a one-minute grid, the sunrise and sunset times, and the
        target position at the start time.
    """
    day_start = Time(int(t0.utc.mjd), format="mjd", scale="utc")
    time = day_start + (np.arange(0, 24 * 60 + 1) << u.min)
    alt = target.transform_to(observer.altaz(time=time)).alt.to(u.deg)
    return TargetVisibility(
        time=time,
        alt=alt,
        sun_rise_time=observer.sun_rise_time(day_start, which="next"),
        sun_set_time=observer.sun_set_time(day_start, which="next"),
        t0=t0,
        altaz_t0=target.transform_to(observer.altaz(time=t0)),
        is_night_t0=bool(observer.is_night(t0)),
    )
