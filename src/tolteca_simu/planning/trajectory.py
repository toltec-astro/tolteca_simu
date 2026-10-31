"""Telescope trajectory of an observation."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import astropy.units as u
import numpy as np
from astroplan import Observer
from astropy.coordinates import ICRS, SkyCoord
from astropy.coordinates.erfa_astrom import ErfaAstromInterpolator, erfa_astrom
from astropy.time import Time
from scipy.interpolate import interp1d

from tolteca_simu.mapping import MappingPattern, RasterPattern

if TYPE_CHECKING:
    from tolteca_datamodels.lmt.tel import LmtTelAccessor

__all__ = ["Trajectory", "get_tel_trajectory", "get_trajectory"]

_F_SMP_DEFAULT = 10 << u.Hz
_N_SAMPLES_MIN = 100
# Interpolating the ERFA astrometry over this interval speeds up the frame
# transformations of long trajectories.
_ERFA_INTERPOLATION_INTERVAL = 300 << u.s


@dataclass(frozen=True)
class Trajectory:
    """Boresight trajectory of an observation.

    The trajectory is rendered from a mapping pattern around a target, or
    replayed from a telescope file.

    Attributes
    ----------
    t : astropy.units.Quantity
        Times since the start.
    time : astropy.time.Time
        Absolute times.
    dlon, dlat : astropy.units.Quantity
        Boresight offsets from the target in the reference frame.
    coords : astropy.coordinates.SkyCoord
        Boresight in the reference frame.
    coords_icrs : astropy.coordinates.SkyCoord
        Boresight in ICRS.
    coords_altaz : astropy.coordinates.SkyCoord
        Boresight in horizon coordinates.
    target_altaz : astropy.coordinates.SkyCoord
        Target in horizon coordinates.
    turnaround : numpy.ndarray
        True off scan: where a raster turns around between scans, or where a
        telescope file records a nonzero hold flag.
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


def get_tel_trajectory(
    tel: "LmtTelAccessor",
    *,
    observer: Observer,
    t: u.Quantity | None = None,
) -> Trajectory:
    """Replay the boresight trajectory recorded in an LMT telescope file.

    Parameters
    ----------
    tel : tolteca_datamodels.lmt.tel.LmtTelAccessor
        The ``lmt_tel`` accessor of a telescope dataset opened with
        `tolteca_datamodels.lmt.open_lmt_tel`. Its times, positions and hold
        flags are read, so the dataset stays open until this returns.
    observer : astroplan.Observer
        The observing site.
    t : astropy.units.Quantity, optional
        Times since the first telescope sample. By default, the telescope
        samples themselves.

    Returns
    -------
    Trajectory
        The trajectory in ICRS, its reference frame, and in horizon coordinates,
        around the file's main target. At requested times, positions interpolate
        linearly between samples and hold flags take the nearest sample.

    Raises
    ------
    ValueError
        If a requested time is outside the recorded samples.
    """
    tel_time = tel.tel_time.to_numpy()
    t_tel = tel_time - tel_time[0]
    # Interpolating continuous right ascensions keeps the samples on either
    # side of 0h together.
    ra_deg = np.unwrap(np.degrees(tel.ra.to_numpy()), period=360.0)
    dec_deg = np.degrees(tel.dec.to_numpy())
    hold_flag = tel.hold_flag.to_numpy()
    if t is None:
        t = t_tel << u.s
    else:
        t_s = t.to_value(u.s)
        ra_deg = interp1d(t_tel, ra_deg)(t_s)
        dec_deg = interp1d(t_tel, dec_deg)(t_s)
        hold_flag = interp1d(t_tel, hold_flag, kind="nearest")(t_s)
    time = Time(tel_time[0], format="unix") + t
    target = tel.meta.target
    coords_icrs = SkyCoord(ra_deg << u.deg, dec_deg << u.deg, frame="icrs")
    offsets = coords_icrs.transform_to(target.skyoffset_frame())
    altaz_frame = observer.altaz(time=time)
    with erfa_astrom.set(ErfaAstromInterpolator(_ERFA_INTERPOLATION_INTERVAL)):
        coords_altaz = coords_icrs.transform_to(altaz_frame)
        target_altaz = target.transform_to(altaz_frame)
    return Trajectory(
        t=t,
        time=time,
        dlon=offsets.lon,
        dlat=offsets.lat,
        coords=coords_icrs,
        coords_icrs=coords_icrs,
        coords_altaz=coords_altaz,
        target_altaz=target_altaz,
        turnaround=hold_flag != 0,
    )
