"""TolTEC detector positions along a boresight trajectory.

The projection follows v1 tolteca ``ToltecSkyProjModel``: detector offsets in
the TolTEC frame turn with the boresight elevation (the M3 mirror) and are
placed around the boresight in horizon coordinates, then transformed to ICRS.
"""

from dataclasses import dataclass

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.coordinates.erfa_astrom import ErfaAstromInterpolator, erfa_astrom

from tolteca_simu.planning.trajectory import Trajectory

__all__ = ["DetectorPositions", "get_detector_positions"]

# Interpolating the ERFA astrometry over this interval speeds up the transform
# to ICRS, as for the boresight trajectory.
_ERFA_INTERPOLATION_INTERVAL = 300 << u.s
# All detectors at one time share the transform from horizon to ICRS offsets,
# smooth across the field. A cubic fitted to a 5 x 5 grid of exactly
# transformed offsets spanning the detectors reproduces per-detector
# transforms to about 1e-13 deg, and costs a fraction of them.
_MAP_DEGREE = 3
_GRID = np.linspace(-1.0, 1.0, _MAP_DEGREE + 2)
_GRID_U, _GRID_V = (g.ravel() for g in np.meshgrid(_GRID, _GRID))
_MAP_POWERS = [(i, d - i) for d in range(_MAP_DEGREE + 1) for i in range(d + 1)]
_MAP_FIT = np.linalg.pinv(
    np.stack([_GRID_U**i * _GRID_V**j for i, j in _MAP_POWERS], axis=1)
)


@dataclass(frozen=True)
class DetectorPositions:
    """Detector positions along a trajectory.

    Attributes
    ----------
    coords_altaz : astropy.coordinates.SkyCoord
        Horizon coordinates, of shape (n_detectors, n_times).
    coords_icrs : astropy.coordinates.SkyCoord
        ICRS coordinates, of the same shape.
    """

    coords_altaz: SkyCoord
    coords_icrs: SkyCoord


def get_detector_positions(
    x_t: u.Quantity, y_t: u.Quantity, trajectory: Trajectory
) -> DetectorPositions:
    """Return the sky positions of detectors along a boresight trajectory.

    Parameters
    ----------
    x_t, y_t : astropy.units.Quantity
        Detector offsets from the boresight in the TolTEC frame, such as the
        ``x_t`` and ``y_t`` columns of an array property table; one per
        detector.
    trajectory : tolteca_simu.planning.Trajectory
        The boresight trajectory, planned or replayed.

    Returns
    -------
    DetectorPositions
        Positions with one row per detector, in input order, and one column
        per trajectory time. Positions at each time depend on that time only.
    """
    altaz = trajectory.coords_altaz
    icrs = trajectory.coords_icrs
    az0, alt0 = altaz.az.radian, altaz.alt.radian
    ra0, dec0 = icrs.ra.radian, icrs.dec.radian
    x = np.asarray(x_t.to_value(u.rad))[:, np.newaxis]
    y = np.asarray(y_t.to_value(u.rad))[:, np.newaxis]
    du = np.cos(alt0) * x - np.sin(alt0) * y
    dv = np.sin(alt0) * x + np.cos(alt0) * y
    az, alt = _offset_to_lonlat(az0, alt0, du, dv)
    # The reference grid spans the detectors at every orientation.
    scale = float(np.max(np.hypot(x, y)))
    grid_az, grid_alt = _offset_to_lonlat(
        az0, alt0, scale * _GRID_U[:, np.newaxis], scale * _GRID_V[:, np.newaxis]
    )
    with erfa_astrom.set(ErfaAstromInterpolator(_ERFA_INTERPOLATION_INTERVAL)):
        grid = SkyCoord(
            grid_az << u.rad,
            grid_alt << u.rad,
            frame=altaz.frame.replicate_without_data(),
        ).transform_to("icrs")
    grid_dra, grid_ddec = _lonlat_to_offset(ra0, dec0, grid.ra.radian, grid.dec.radian)
    dra = np.zeros(du.shape)
    ddec = np.zeros(du.shape)
    for (i, j), c_ra, c_dec in zip(
        _MAP_POWERS, _MAP_FIT @ grid_dra, _MAP_FIT @ grid_ddec, strict=True
    ):
        term = (du / scale) ** i * (dv / scale) ** j
        dra += c_ra * term
        ddec += c_dec * term
    ra, dec = _offset_to_lonlat(ra0, dec0, dra, ddec)
    return DetectorPositions(
        coords_altaz=SkyCoord(
            az << u.rad, alt << u.rad, frame=altaz.frame.replicate_without_data()
        ),
        coords_icrs=SkyCoord(ra << u.rad, dec << u.rad, frame="icrs"),
    )


def _offset_to_lonlat(
    lon0: np.ndarray, lat0: np.ndarray, dlon: np.ndarray, dlat: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    # Spherical offsets around (lon0, lat0), in radians, to absolute angles;
    # the transform of astropy's SkyOffsetFrame.
    x = np.cos(dlat) * np.cos(dlon)
    y = np.cos(dlat) * np.sin(dlon)
    z = np.sin(dlat)
    cos0, sin0 = np.cos(lat0), np.sin(lat0)
    x, z = cos0 * x - sin0 * z, sin0 * x + cos0 * z
    lon = np.mod(lon0 + np.arctan2(y, x), 2 * np.pi)
    return lon, np.arctan2(z, np.hypot(x, y))


def _lonlat_to_offset(
    lon0: np.ndarray, lat0: np.ndarray, lon: np.ndarray, lat: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    # The inverse of _offset_to_lonlat.
    x = np.cos(lat) * np.cos(lon - lon0)
    y = np.cos(lat) * np.sin(lon - lon0)
    z = np.sin(lat)
    cos0, sin0 = np.cos(lat0), np.sin(lat0)
    x, z = cos0 * x + sin0 * z, -sin0 * x + cos0 * z
    return np.arctan2(y, x), np.arctan2(z, np.hypot(x, y))
