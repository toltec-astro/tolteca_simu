"""Target elevation over the observing day."""

from dataclasses import dataclass

import astropy.units as u
import numpy as np
from astroplan import (
    AltitudeConstraint,
    AtNightConstraint,
    FixedTarget,
    Observer,
    observability_table,
)
from astropy.coordinates import SkyCoord
from astropy.time import Time

__all__ = [
    "TargetUptime",
    "TargetVisibility",
    "get_target_uptime",
    "get_target_visibility",
]


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
    """

    time: Time
    alt: u.Quantity
    sun_rise_time: Time
    sun_set_time: Time
    t0: Time


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
        Altitudes on a one-minute grid and the sunrise and sunset times.
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
    )


@dataclass(frozen=True)
class TargetUptime:
    """Time a target is observable on a UT day.

    Attributes
    ----------
    uptime : astropy.units.Quantity
        Time at night with the target above the lowest usable elevation,
        sampled every 30 minutes.
    transit_time : astropy.time.Time
        Meridian transit nearest to the start of the day.
    """

    uptime: u.Quantity
    transit_time: Time


def get_target_uptime(
    target: SkyCoord, date: Time, observer: Observer, alt_min: u.Quantity
) -> TargetUptime | None:
    """Return how long a target is observable on a UT day.

    The day is sampled every 30 minutes from ``date``; a sample is observable
    at night (Sun below the horizon) with the target at or above ``alt_min``.

    Parameters
    ----------
    target : astropy.coordinates.SkyCoord
        The target coordinate.
    date : astropy.time.Time
        Start of the UT day.
    observer : astroplan.Observer
        The observing site.
    alt_min : astropy.units.Quantity
        Lowest usable elevation.

    Returns
    -------
    TargetUptime or None
        The up-time and the transit, or None if the target is never
        observable that day.
    """
    constraints = [AltitudeConstraint(alt_min, 91 * u.deg), AtNightConstraint()]
    fixed_target = FixedTarget(coord=target)
    summary = observability_table(
        constraints,
        observer,
        [fixed_target],
        times=date + (np.arange(0, 24, 0.5) << u.h),
    )
    if not summary["ever observable"][0]:
        return None
    return TargetUptime(
        uptime=(summary["fraction of time observable"][0] * 24) << u.h,
        transit_time=observer.target_meridian_transit_time(
            date, fixed_target, n_grid_points=48
        ),
    )
