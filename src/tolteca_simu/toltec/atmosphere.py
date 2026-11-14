"""TolTEC detector power from the turbulent atmosphere.

The turbulent atmosphere of `tolteca_simu.atmosphere` adds power to the static
atmosphere background of the loading model. Its spectrum comes from TOAST's
atmosphere model, at the PWV that matches the loading model's atmosphere, and
reaches the detectors with the efficiency of the background's atmosphere term.
This requires the ``toast`` extra, ``tolteca_simu[toast]``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

import astropy.units as u
import numpy as np
from scipy.optimize import brentq

from tolteca_simu.lmt import get_lmt_observer

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from numpy.typing import ArrayLike

    from tolteca_simu.atmosphere import SiteWeather, ToastAtmosphere

    from .info import ToltecArrayName
    from .sensitivity import ToltecArrayLoadingModel

__all__ = ["AtmospherePower", "get_matched_pwv"]

# TOAST evaluates the atmosphere spectrum at this many frequencies across a
# passband and interpolates linearly between them (the n_bandpass_freqs default
# of TOAST 3.0.6 ObserveAtmosphere).
_N_BAND_FREQS = 100
# PWV search range and tolerance.
_PWV_RANGE_MM = (0.0, 30.0)
_PWV_XTOL_MM = 1e-4


def get_matched_pwv(
    loading_models: Mapping[ToltecArrayName, ToltecArrayLoadingModel],
    weather: SiteWeather,
) -> u.Quantity:
    """Return the PWV at which TOAST's atmosphere matches the atmosphere model.

    TOAST's atmosphere model gives the brightness of the atmosphere at the
    zenith from the PWV and the weather. At the matched PWV, this brightness,
    scaled to the highest altitude of the atmosphere model table, gives the
    same atmosphere power on the detectors as the loading models' atmosphere
    model, on average over the arrays.

    Parameters
    ----------
    loading_models : dict of ToltecArrayLoadingModel
        Loading model by array name, for one atmosphere model.
    weather : tolteca_simu.atmosphere.SiteWeather
        Weather at the telescope; its pressure and air temperature are used.

    Returns
    -------
    astropy.units.Quantity
        PWV in mm, to 1e-4 mm.
    """
    # TOAST is an optional dependency of tolteca_simu.
    from toast.atm import atm_atmospheric_loading_vec  # noqa: PLC0415

    references = []
    for model in loading_models.values():
        alt = model.alt_range[1]
        references.append(
            (
                model,
                1.0 / np.sin(alt.to_value(u.rad)),
                model.get_atmosphere_power(model.get_atmosphere_brightness(alt)),
            )
        )

    def get_mean_excess(pwv_mm: float) -> float:
        return (
            np.mean(
                [
                    (
                        model.get_atmosphere_power(
                            _eval_toast_spectrum(
                                atm_atmospheric_loading_vec, model, weather, pwv_mm
                            )
                            * airmass
                            << u.K
                        )
                        / power
                    ).to_value(u.one)
                    for model, airmass, power in references
                ]
            )
            - 1.0
        )

    return brentq(get_mean_excess, *_PWV_RANGE_MM, xtol=_PWV_XTOL_MM) << u.mm


@dataclass(frozen=True)
class AtmospherePower:
    """Detector power from a TOAST atmosphere, per array.

    Attributes
    ----------
    pwv : astropy.units.Quantity
        PWV of the atmosphere, from `get_matched_pwv`.
    power_scale : dict of astropy.units.Quantity
        Detector power per unit of TOAST's line-of-sight integral, by array
        name.
    """

    pwv: u.Quantity
    power_scale: Mapping[ToltecArrayName, u.Quantity]

    @classmethod
    def from_atmosphere(
        cls,
        atmosphere: ToastAtmosphere,
        loading_models: Mapping[ToltecArrayName, ToltecArrayLoadingModel],
    ) -> Self:
        """Prepare the detector power of a TOAST atmosphere.

        TOAST's line-of-sight integral times the gain and the atmosphere
        absorption coefficient at a frequency is the brightness temperature of
        the atmosphere. Its power is the atmosphere term of the loading model,
        `ToltecArrayLoadingModel.get_atmosphere_power`. The absorption
        coefficient is that of TOAST's atmosphere model at the weather of the
        atmosphere and the matched PWV.

        Parameters
        ----------
        atmosphere : tolteca_simu.atmosphere.ToastAtmosphere
            The atmosphere, for its weather and gain.
        loading_models : dict of ToltecArrayLoadingModel
            Loading model by array name, for one atmosphere model.

        Returns
        -------
        AtmospherePower
            The power scale of each array.
        """
        # TOAST is an optional dependency of tolteca_simu.
        from toast.atm import atm_absorption_coefficient_vec  # noqa: PLC0415

        pwv = get_matched_pwv(loading_models, atmosphere.weather)
        gain = atmosphere.config.gain
        return cls(
            pwv=pwv,
            power_scale={
                name: model.get_atmosphere_power(
                    gain
                    * _eval_toast_spectrum(
                        atm_absorption_coefficient_vec,
                        model,
                        atmosphere.weather,
                        pwv.to_value(u.mm),
                    )
                    << u.K
                )
                for name, model in loading_models.items()
            },
        )

    def evaluate(self, array_name: ArrayLike, raw: np.ndarray) -> u.Quantity:
        """Return the detector power for TOAST's line-of-sight integral.

        Parameters
        ----------
        array_name : array_like of str
            Array name of each detector.
        raw : numpy.ndarray
            Line-of-sight integral, of shape (n_detectors, n_times), from
            `tolteca_simu.atmosphere.ToastAtmosphere.observe`.

        Returns
        -------
        astropy.units.Quantity
            Power in pW, of the shape of ``raw``, to add to the power of
            `get_detector_loading`.

        Raises
        ------
        KeyError
            A detector's array has no power scale.
        """
        scale = np.array(
            [self.power_scale[name].to_value(u.pW) for name in np.asarray(array_name)]
        )
        return (scale[:, np.newaxis] * raw) << u.pW


def _eval_toast_spectrum(
    func: Callable[..., np.ndarray],
    model: ToltecArrayLoadingModel,
    weather: SiteWeather,
    pwv_mm: float,
) -> np.ndarray:
    # A spectrum of TOAST's atmosphere model at the LMT, at the passband
    # frequencies, interpolated as TOAST does.
    f_ghz = model.f_passband.to_value(u.GHz)
    f_band_ghz = np.linspace(f_ghz[0], f_ghz[-1], _N_BAND_FREQS)
    values = func(
        get_lmt_observer().location.height.to_value(u.m),
        weather.air_temperature.to_value(u.K, equivalencies=u.temperature()),
        weather.pressure.to_value(u.Pa),
        pwv_mm,
        f_band_ghz[0],
        f_band_ghz[-1],
        _N_BAND_FREQS,
    )
    return np.interp(f_ghz, f_band_ghz, values)
