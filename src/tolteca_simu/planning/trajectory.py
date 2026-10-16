"""Telescope trajectory of an observation."""

from dataclasses import dataclass
from typing import Literal

import astropy.units as u
import numpy as np
from astroplan import Observer
from astropy.coordinates import ICRS, SkyCoord
from astropy.coordinates.erfa_astrom import ErfaAstromInterpolator, erfa_astrom
from astropy.time import Time

from tolteca_simu.mapping import MappingPattern, RasterPattern

__all__ = ["Trajectory", "get_trajectory"]

_F_SMP_DEFAULT = 10 << u.Hz
_N_SAMPLES_MIN = 100
# Interpolating the ERFA astrometry over this interval speeds up the frame
# transformations of long trajectories.
_ERFA_INTERPOLATION_INTERVAL = 300 << u.s


@dataclass(frozen=True)
class Trajectory:
    """Boresight trajectory of a mapping pattern rendered around a target.

    Attributes
    ----------
    t : astropy.units.Quantity
        Times since the start.
    time : astropy.time.Time
        Absolute times.
    dlon, dlat : astropy.units.Quantity
        Pattern offsets in the reference frame.
    coords : astropy.coordinates.SkyCoord
        Boresight in the reference frame.
    coords_icrs : astropy.coordinates.SkyCoord
        Boresight in ICRS.
    coords_altaz : astropy.coordinates.SkyCoord
        Boresight in horizon coordinates.
    target_altaz : astropy.coordinates.SkyCoord
        Target in horizon coordinates.
    turnaround : numpy.ndarray
        True where a raster turns around between scans.
    """

    t: u.Quantity
    time: Time
    dlon: u.Quantity
    dlat: u.Quantity
    coords: SkyCoord
    coords_icrs: SkyCoord
    coords_altaz: SkyCoord
    target_altaz: SkyCoord
    turnaround: np.ndarray


def get_trajectory(  # noqa: PLR0913
    pattern: MappingPattern,
    target: SkyCoord,
    t0: Time,
    *,
    t_exp: u.Quantity,
    ref_frame: Literal["altaz", "icrs"],
    observer: Observer,
    f_smp: u.Quantity = _F_SMP_DEFAULT,
) -> Trajectory:
    """Render a mapping pattern around a target.

    Parameters
    ----------
    pattern : tolteca_simu.mapping.MappingPattern
        The mapping pattern.
    target : astropy.coordinates.SkyCoord
        The target the pattern is centered on.
    t0 : astropy.time.Time
        Start time.
    t_exp : astropy.units.Quantity
        Duration to render.
    ref_frame : {"altaz", "icrs"}
        Frame in which the pattern offsets are interpreted. Horizon offsets are
        applied at each sample time.
    observer : astroplan.Observer
        The observing site.
    f_smp : astropy.units.Quantity, optional
        Sampling rate; at least 100 samples are drawn.

    Returns
    -------
    Trajectory
        The trajectory in the reference frame, ICRS and horizon coordinates.
    """
    t_exp_s = t_exp.to_value(u.s)
    dt_smp_s = (1.0 / f_smp).to_value(u.s)
    t = np.arange(0, t_exp_s + dt_smp_s, dt_smp_s) << u.s
    if t.size < _N_SAMPLES_MIN:
        t = np.linspace(0, t_exp_s, _N_SAMPLES_MIN) << u.s
    time = t0 + t
    dlon, dlat = pattern.offsets(t)
    frame = observer.altaz(time=time) if ref_frame == "altaz" else ICRS()
    offset_frame = target.transform_to(frame).skyoffset_frame()
    coords = SkyCoord(dlon, dlat, frame=offset_frame).transform_to(frame)
    if isinstance(pattern, RasterPattern):
        turnaround = pattern.turnaround_mask(t)
    else:
        turnaround = np.zeros(t.shape, dtype=bool)
    altaz_frame = observer.altaz(time=time)
    with erfa_astrom.set(ErfaAstromInterpolator(_ERFA_INTERPOLATION_INTERVAL)):
        coords_icrs = coords.transform_to("icrs")
        coords_altaz = coords.transform_to(altaz_frame)
        target_altaz = target.transform_to(altaz_frame)
    return Trajectory(
        t=t,
        time=time,
        dlon=dlon,
        dlat=dlat,
        coords=coords,
        coords_icrs=coords_icrs,
        coords_altaz=coords_altaz,
        target_altaz=target_altaz,
        turnaround=turnaround,
    )
