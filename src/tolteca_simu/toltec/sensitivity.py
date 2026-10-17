"""TolTEC detector loading, noise, and map sensitivity.

The power-loading model follows v1 tolteca ``ToltecArrayPowerLoadingModel``,
itself based on the TolTEC mapping-speed calculator: an LMT am atmosphere
model, warm and cold optics, the array passband, and the Ruze efficiency of the
primary surface. Detector noise factors scale the photon noise empirically.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING

import astropy.units as u
import numpy as np

# h, k_B and c are exact SI values in every CODATA release since 2018. This
# module defines them statically; astropy.constants fills its names at import.
from astropy.constants import codata2018 as const
from astropy.cosmology import default_cosmology
from astropy.modeling.functional_models import GAUSSIAN_SIGMA_TO_FWHM
from scipy.interpolate import RectBivariateSpline

if TYPE_CHECKING:
    from astropy.table import QTable

    from .coverage import CoverageMap
    from .info import ToltecArrayInfo

__all__ = [
    "POLARIZED_NOISE_FACTOR",
    "ArrayNoise",
    "MapDepth",
    "ToltecArrayLoadingModel",
    "beam_area",
    "get_map_depth",
]

POLARIZED_NOISE_FACTOR = 2**0.5 + 0.1
"""Noise factor of polarized intensity over total intensity.

Measuring Stokes Q and U separately doubles the time to reach a given error
(a factor of sqrt(2) in noise); imperfect modulation adds 0.1.
"""

# Instrument parameters, independent of frequency.
_DET_OPTICAL_EFFICIENCY = 0.8
_HORN_APERTURE_EFFICIENCY = 0.35
_TEL_DIAMETER = 48.0 << u.m
_TEL_EMISSIVITY = 0.06
_T_COLDBOX = 5.75 << u.K
_T_TEL = 273.0 << u.K
_T_COUPLING_OPTICS = 290.0 << u.K
_TEL_AREA = np.pi * (_TEL_DIAMETER / 2.0) ** 2
_T_WARM = _TEL_EMISSIVITY * _T_TEL + 3.0 * _T_COUPLING_OPTICS * 0.01
_COLD_EFFICIENCY = _DET_OPTICAL_EFFICIENCY * _HORN_APERTURE_EFFICIENCY
_T_DET_WARM = _T_WARM * _COLD_EFFICIENCY
_T_DET_COLDBOX = (
    _T_COLDBOX * _DET_OPTICAL_EFFICIENCY * (1.0 - _HORN_APERTURE_EFFICIENCY)
)


def beam_area(array: ToltecArrayInfo) -> u.Quantity:
    """Return the solid angle of an array's Gaussian beam.

    Parameters
    ----------
    array : tolteca_simu.toltec.ToltecArrayInfo
        The array.

    Returns
    -------
    astropy.units.Quantity
        ``2 pi sigma_a sigma_b``.
    """
    a_stddev = array.a_fwhm / GAUSSIAN_SIGMA_TO_FWHM
    b_stddev = array.b_fwhm / GAUSSIAN_SIGMA_TO_FWHM
    return 2 * np.pi * a_stddev * b_stddev


@dataclass(frozen=True)
class ArrayNoise:
    """Passband-integrated detector noise.

    Attributes
    ----------
    net_cmb : astropy.units.Quantity
        Noise equivalent CMB temperature.
    nefd : astropy.units.Quantity
        Noise equivalent flux density, for total intensity.
    nep : astropy.units.Quantity
        Noise equivalent power.
    """

    net_cmb: u.Quantity
    nefd: u.Quantity
    nep: u.Quantity


class ToltecArrayLoadingModel:
    """Optical loading and noise of one TolTEC array at an altitude.

    Parameters
    ----------
    array : tolteca_simu.toltec.ToltecArrayInfo
        The array.
    passband : astropy.table.QTable
        Passband with a uniform frequency grid ``f`` and ``throughput``.
    atm_table : dict of numpy.ndarray
        LMT am atmosphere model table: ``atmFreq`` (GHz), ``el`` (deg),
        ``atmTRJ`` (K) and ``atmTtx``.
    tel_surface_rms : astropy.units.Quantity
        RMS of the primary surface.
    det_noise_factor : float
        Detector noise relative to photon noise; the total noise is the photon
        noise times ``sqrt(1 + det_noise_factor**2)``.

    Raises
    ------
    ValueError
        If the passband frequency grid is not uniform.
    """

    def __init__(
        self,
        array: ToltecArrayInfo,
        passband: QTable,
        atm_table: dict[str, np.ndarray],
        tel_surface_rms: u.Quantity,
        det_noise_factor: float,
    ) -> None:
        self._array = array
        self._f = passband["f"]
        df = np.diff(self._f).value
        if np.std(df) / df[0] > 1e-7:  # noqa: PLR2004
            msg = "Passband frequency grid has to be uniform"
            raise ValueError(msg)
        self._df = self._f[1] - self._f[0]
        self._throughput = np.asarray(passband["throughput"])
        f_ghz = atm_table["atmFreq"][:, 0]
        el = atm_table["el"]
        self._atm_t = RectBivariateSpline(f_ghz, el, atm_table["atmTRJ"])
        self._atm_tx = RectBivariateSpline(f_ghz, el, atm_table["atmTtx"])
        self._tel_surface_rms = tel_surface_rms
        self._det_noise_factor = det_noise_factor

    @property
    def array(self) -> ToltecArrayInfo:
        """The array."""
        return self._array

    def _eval_atm(self, interp: RectBivariateSpline, alt: u.Quantity) -> np.ndarray:
        f, a = np.meshgrid(self._f, np.atleast_1d(alt), indexing="ij")
        return np.squeeze(interp(f.to_value(u.GHz), a.to_value(u.deg), grid=False).T)

    @cached_property
    def _system_efficiency(self) -> np.ndarray:
        # The Ruze efficiency of the primary surface.
        ruze = np.exp(
            -(((4.0 * np.pi * self._tel_surface_rms) / (const.c / self._f)) ** 2)
        )
        return ruze * _COLD_EFFICIENCY * self._throughput

    def _get_t_det(self, alt: u.Quantity) -> u.Quantity:
        t_atm = self._eval_atm(self._atm_t, alt) << u.K
        return (
            t_atm * _COLD_EFFICIENCY + _T_DET_WARM + _T_DET_COLDBOX
        ) * self._throughput

    def _t_to_dp(self, t: u.Quantity) -> u.Quantity:
        return const.k_B * t * self._df

    def _t_to_dnep(self, t: u.Quantity) -> u.Quantity:
        dp = self._t_to_dp(t)
        shot = 2.0 * const.k_B * t * const.h * self._f * self._df
        wave = 2.0 * dp**2 / self._df
        return np.sqrt(shot + wave)

    def get_power(self, alt: u.Quantity) -> u.Quantity:
        """Return the detector power loading.

        Parameters
        ----------
        alt : astropy.units.Quantity
            Scalar altitude.

        Returns
        -------
        astropy.units.Quantity
            Power in pW.
        """
        return u.Quantity(np.nansum(self._t_to_dp(self._get_t_det(alt)), axis=-1)).to(
            u.pW
        )

    def get_noise(self, alt: u.Quantity) -> ArrayNoise:
        """Return the passband-integrated noise.

        Parameters
        ----------
        alt : astropy.units.Quantity
            Scalar altitude.

        Returns
        -------
        ArrayNoise
            NET, NEFD and NEP, combined over the passband bins.
        """
        t_det = self._get_t_det(alt)
        noise_coeff = np.sqrt(1.0 + self._det_noise_factor**2)
        dnep = self._t_to_dnep(t_det) * noise_coeff
        tx_atm = self._eval_atm(self._atm_tx, alt)
        f = self._f
        df = self._df
        x = const.h * f / (const.k_B * default_cosmology.get().Tcmb(0))
        net_integrand = (
            (const.k_B * x) ** 2.0
            * (1.0 / const.k_B)
            * np.exp(x)
            / (np.expm1(x)) ** 2.0
        )
        dnet_cmb = (
            self._t_to_dnep(t_det)
            / (np.sqrt(2.0) * self._system_efficiency * net_integrand * df)
            / tx_atm
            * noise_coeff
        )
        dnefd = (
            dnep / (_TEL_AREA * df) / self._system_efficiency * np.sqrt(2.0) / tx_atm
        )
        return ArrayNoise(
            net_cmb=np.sqrt(1.0 / np.nansum(dnet_cmb ** (-2.0), axis=-1)).to(
                u.mK * u.Hz**-0.5
            ),
            nefd=np.sqrt(1.0 / np.nansum(dnefd ** (-2.0), axis=-1)).to(
                u.mJy * u.Hz**-0.5
            ),
            nep=np.sqrt(np.nansum(dnep**2.0, axis=-1)).to(u.aW * u.Hz**-0.5),
        )

    def get_mapping_speed(self, alt: u.Quantity, n_dets: int) -> u.Quantity:
        """Return the total-intensity mapping speed.

        Parameters
        ----------
        alt : astropy.units.Quantity
            Scalar altitude.
        n_dets : int
            Number of detectors.

        Returns
        -------
        astropy.units.Quantity
            ``n_dets * beam_area / nefd**2`` in deg2 / mJy2 / h.
        """
        nefd = self.get_noise(alt).nefd
        return ((1 / nefd) ** 2 * n_dets * beam_area(self._array)).to(
            u.deg**2 / u.mJy**2 / u.hr
        )


@dataclass(frozen=True)
class MapDepth:
    """Map depth from a coverage map.

    Attributes
    ----------
    depth : numpy.ndarray
        RMS depth per pixel in mJy/beam, zero where coverage is below 2 % of
        its maximum.
    depth_all : numpy.ndarray
        As ``depth``, from the coverage including raster turnarounds.
    map_area : astropy.units.Quantity
        Area with coverage above 10 % of the maximum.
    depth_rms : astropy.units.Quantity
        Median depth over that area.
    """

    depth: np.ndarray
    depth_all: np.ndarray
    map_area: u.Quantity
    depth_rms: u.Quantity


def get_map_depth(
    coverage: CoverageMap, nefd: u.Quantity, array: ToltecArrayInfo
) -> MapDepth:
    """Convert a coverage map to map depth.

    Parameters
    ----------
    coverage : tolteca_simu.toltec.CoverageMap
        Coverage in seconds per pixel; the turnaround-free coverage sets the
        masks and the depth.
    nefd : astropy.units.Quantity
        Noise equivalent flux density for the measured Stokes parameters.
    array : tolteca_simu.toltec.ToltecArrayInfo
        The array, for its beam.

    Returns
    -------
    MapDepth
        Depth maps, map area, and median depth.
    """
    cov = coverage.data_on_scan
    pixarea = coverage.wcs.proj_plane_pixel_area()
    cov_max = cov.max()
    m_cov = cov > 0.02 * cov_max
    m_cov_01 = cov > 0.1 * cov_max
    beam_area_pix2 = (beam_area(array) / pixarea).to_value(u.dimensionless_unscaled)
    nefd_value = nefd.to_value(u.mJy * u.s**0.5)

    def _depth(data: np.ndarray) -> np.ndarray:
        depth = np.zeros(data.shape, dtype="d")
        depth[m_cov] = np.sqrt(2.0) * nefd_value / np.sqrt(data[m_cov] * beam_area_pix2)
        return depth

    depth = _depth(cov)
    return MapDepth(
        depth=depth,
        depth_all=_depth(coverage.data),
        map_area=(m_cov_01.sum() * pixarea).to(u.deg**2),
        depth_rms=np.median(depth[m_cov_01]) << u.mJy,
    )
