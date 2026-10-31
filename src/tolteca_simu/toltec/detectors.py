"""TolTEC detector positions along a boresight trajectory.

The projection follows v1 tolteca ``ToltecSkyProjModel``: detector offsets in
the TolTEC frame turn with the boresight elevation (the M3 mirror) and are
placed around the boresight in horizon coordinates.
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
        per trajectory time.
    """
    altaz = trajectory.coords_altaz
    alt = altaz.alt.radian
    cos_alt = np.cos(alt)[np.newaxis, :]
    sin_alt = np.sin(alt)[np.newaxis, :]
    x = np.asanyarray(x_t)[:, np.newaxis]
    y = np.asanyarray(y_t)[:, np.newaxis]
    with erfa_astrom.set(ErfaAstromInterpolator(_ERFA_INTERPOLATION_INTERVAL)):
        coords_altaz = SkyCoord(
            cos_alt * x - sin_alt * y,
            sin_alt * x + cos_alt * y,
            frame=altaz.skyoffset_frame(),
        ).transform_to(altaz.frame)
        coords_icrs = coords_altaz.transform_to("icrs")
    return DetectorPositions(coords_altaz=coords_altaz, coords_icrs=coords_icrs)
