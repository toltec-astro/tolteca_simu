"""TolTEC array footprint and sky coverage of an observation."""

from dataclasses import dataclass

import astropy.units as u
import numpy as np
from astroplan import Observer
from astropy.convolution import Gaussian2DKernel, convolve_fft
from astropy.coordinates import SkyCoord
from astropy.modeling.functional_models import GAUSSIAN_SIGMA_TO_FWHM
from astropy.table import QTable
from astropy.wcs import WCS

from tolteca_simu.planning.trajectory import Trajectory
from tolteca_simu.sky import SkyBoundingBox, make_wcs

from .info import TOLTEC_PLATE_SCALE, ToltecArrayInfo

__all__ = [
    "CoverageMap",
    "Footprint",
    "get_array_outline",
    "get_coverage_map",
    "get_footprint",
    "place_on_sky",
]

_PIXSCALE = 4.0 << u.arcsec / u.pix
_N_PIX_MAX = 1e6
_ADAPTIVE_PIXSCALE_FACTOR = 0.5
_PADDING = 2 << u.arcmin


@dataclass(frozen=True)
class Footprint:
    """Detectors of one array placed on the sky.

    Attributes
    ----------
    dlon, dlat : astropy.units.Quantity
        Detector offsets from the boresight.
    pg : numpy.ndarray
        Polarization group of each detector.
    coords_icrs : astropy.coordinates.SkyCoord
        Detector positions when the boresight is closest to the target.
    """

    dlon: u.Quantity
    dlat: u.Quantity
    pg: np.ndarray
    coords_icrs: SkyCoord


@dataclass(frozen=True)
class CoverageMap:
    """Time each sky pixel is observed by an array.

    Attributes
    ----------
    wcs : astropy.wcs.WCS
        The image grid.
    data : numpy.ndarray
        Coverage in seconds per pixel.
    data_on_scan : numpy.ndarray
        Coverage excluding raster turnarounds, in seconds per pixel.
    """

    wcs: WCS
    data: np.ndarray
    data_on_scan: np.ndarray


def get_array_outline(
    apt_designed: QTable, array: ToltecArrayInfo
) -> tuple[u.Quantity, u.Quantity]:
    """Return the outline of a designed array as offsets from the boresight.

    The designed positions of the array's edge detectors are projected to the
    sky: reflected, rotated by the array's mounting angle, and scaled by the
    plate scale.

    Parameters
    ----------
    apt_designed : astropy.table.QTable
        Designed array property table with ``x`` and ``y`` positions and the
        ``edge_indices`` of the outline, in order, in its metadata.
    array : tolteca_simu.toltec.ToltecArrayInfo
        The array.

    Returns
    -------
    dlon : astropy.units.Quantity
        Longitude offsets of the outline vertices, in degrees.
    dlat : astropy.units.Quantity
        Latitude offsets of the outline vertices, in degrees.
    """
    edges = apt_designed[apt_designed.meta["edge_indices"]]
    xy = np.vstack([edges["x"].to_value(u.mm), edges["y"].to_value(u.mm)])
    angle = array.mounting_angle.to_value(u.rad)
    rotation = np.array(
        [[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]]
    )
    dlon, dlat = (rotation @ np.diag([1.0, -1.0]) @ xy) * TOLTEC_PLATE_SCALE.to_value(
        u.deg / u.mm
    )
    return dlon << u.deg, dlat << u.deg


def place_on_sky(
    dlon: u.Quantity,
    dlat: u.Quantity,
    trajectory: Trajectory,
    target: SkyCoord,
    observer: Observer,
) -> SkyCoord:
    """Place offsets from the boresight on the sky at the target.

    The offsets are taken in horizon coordinates around the boresight sample
    closest to the target, at that sample's time.

    Parameters
    ----------
    dlon, dlat : astropy.units.Quantity
        Offsets from the boresight.
    trajectory : tolteca_simu.planning.Trajectory
        The boresight trajectory.
    target : astropy.coordinates.SkyCoord
        The target.
    observer : astroplan.Observer
        The observing site.

    Returns
    -------
    astropy.coordinates.SkyCoord
        Sky positions in ICRS.
    """
    i_closest = np.argmin(target.icrs.separation(trajectory.coords_icrs))
    altaz = trajectory.coords_altaz
    center = SkyCoord(
        az=altaz.az[i_closest],
        alt=altaz.alt[i_closest],
        frame=observer.altaz(time=trajectory.time[i_closest]),
    )
    coords_altaz = SkyCoord(dlon, dlat, frame=center.skyoffset_frame()).transform_to(
        center.frame
    )
    return coords_altaz.transform_to("icrs")


def get_footprint(
    apt: QTable,
    array: ToltecArrayInfo,
    trajectory: Trajectory,
    target: SkyCoord,
    observer: Observer,
) -> Footprint:
    """Place an array's detectors on the sky at the target.

    The array is drawn around the boresight sample closest to the target, in
    horizon coordinates at that sample's time (see `place_on_sky`).

    Parameters
    ----------
    apt : astropy.table.QTable
        Array property table with ``array``, ``pg``, ``x_t`` and ``y_t``.
    array : tolteca_simu.toltec.ToltecArrayInfo
        The array to place.
    trajectory : tolteca_simu.planning.Trajectory
        The boresight trajectory.
    target : astropy.coordinates.SkyCoord
        The target.
    observer : astroplan.Observer
        The observing site.

    Returns
    -------
    Footprint
        Detector offsets and sky positions.
    """
    apt_array = apt[np.asarray(apt["array"]) == array.index]
    dlon = apt_array["x_t"]
    dlat = apt_array["y_t"]
    return Footprint(
        dlon=dlon,
        dlat=dlat,
        pg=np.asarray(apt_array["pg"]),
        coords_icrs=place_on_sky(dlon, dlat, trajectory, target, observer),
    )


def _bins(lo: float, hi: float) -> np.ndarray:
    lo_i = int(np.floor(lo))
    hi_i = int(np.ceil(hi))
    if (hi_i + 1 - lo_i) % 2 == 1:
        hi_i += 1
    return np.arange(lo_i, hi_i + 1)


def get_coverage_map(
    trajectory: Trajectory, footprint: Footprint, array: ToltecArrayInfo
) -> CoverageMap:
    """Accumulate the time an array observes each sky pixel.

    The boresight track is binned on a 4 arcsec TAN grid (coarsened to at most
    a million pixels), convolved with the detector layout, and then with the
    beam when the beam spans more than a pixel.

    Parameters
    ----------
    trajectory : tolteca_simu.planning.Trajectory
        The boresight trajectory.
    footprint : Footprint
        The array's detectors.
    array : tolteca_simu.toltec.ToltecArrayInfo
        The array, for its beam.

    Returns
    -------
    CoverageMap
        Coverage with and without raster turnarounds.
    """
    icrs = trajectory.coords_icrs
    det_icrs = footprint.coords_icrs
    bs_bbox = SkyBoundingBox.from_lonlat(icrs.ra, icrs.dec)
    det_bbox = SkyBoundingBox.from_lonlat(det_icrs.ra, det_icrs.dec)
    wcs, (nx, ny) = make_wcs(
        bs_bbox.pad_with(det_bbox.width + _PADDING, det_bbox.height + _PADDING),
        pixscale=_PIXSCALE,
        n_pix_max=_N_PIX_MAX,
        adaptive_pixscale_factor=_ADAPTIVE_PIXSCALE_FACTOR,
    )
    bs_xy = wcs.world_to_pixel_values(icrs.ra.degree, icrs.dec.degree)
    turnaround = trajectory.turnaround
    det_xy = wcs.world_to_pixel_values(det_icrs.ra.degree, det_icrs.dec.degree)
    xbins = np.arange(nx + 1)
    ybins = np.arange(ny + 1)
    bs_im, _, _ = np.histogram2d(bs_xy[1], bs_xy[0], bins=[ybins, xbins])
    bs_im_turnaround, _, _ = np.histogram2d(
        bs_xy[1][turnaround], bs_xy[0][turnaround], bins=[ybins, xbins]
    )
    bs_im *= (trajectory.time[1] - trajectory.time[0]).to_value(u.s)
    bs_im_on_scan = bs_im.copy()
    bs_im_on_scan[bs_im_turnaround > 0] = 0
    det_im, _, _ = np.histogram2d(
        det_xy[1],
        det_xy[0],
        bins=[
            _bins(det_xy[1].min(), det_xy[1].max()),
            _bins(det_xy[0].min(), det_xy[0].max()),
        ],
    )
    cov = convolve_fft(bs_im, det_im, normalize_kernel=False, allow_huge=True)
    cov_on_scan = convolve_fft(
        bs_im_on_scan, det_im, normalize_kernel=False, allow_huge=True
    )
    # The beam is sized with the nominal pixel scale, as in v1.
    equivalencies = u.pixel_scale(_PIXSCALE)
    a_stddev_pix = (array.a_fwhm / GAUSSIAN_SIGMA_TO_FWHM).to_value(
        u.pix, equivalencies=equivalencies
    )
    b_stddev_pix = (array.b_fwhm / GAUSSIAN_SIGMA_TO_FWHM).to_value(
        u.pix, equivalencies=equivalencies
    )
    if a_stddev_pix > 1:
        beam = Gaussian2DKernel(a_stddev_pix, b_stddev_pix)
        cov = convolve_fft(cov, beam, normalize_kernel=False)
        cov_on_scan = convolve_fft(cov_on_scan, beam, normalize_kernel=False)
    return CoverageMap(wcs=wcs, data=cov, data_on_scan=cov_on_scan)
