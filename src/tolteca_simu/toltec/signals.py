"""TolTEC detector signals along a trajectory.

Optical power on each detector (sources, atmosphere and instrument background,
and white power noise) and the KIDs readout signal that the power produces,
for a KIDs model table of TolTECA's physical model families.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING

import astropy.units as u
import numpy as np

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from astropy.table import Table
    from numpy.typing import ArrayLike
    from tolteca_kidsproc.models import KidsSweepWithAffineGain, KidsSweepWithDelayGain

    from .info import ToltecArrayName
    from .sensitivity import ToltecArrayLoadingModel

__all__ = [
    "DetectorLoading",
    "KidsSignals",
    "get_detector_loading",
    "get_kids_signals",
    "realize_power_noise",
]

# Loading quantities are smooth in altitude within the atmosphere table. They
# are evaluated exactly at multiples of this step and interpolated with cubic
# weights on four knots inside the table range, so a value depends only on its
# altitude, wherever the observation is split.
_ALT_STEP_DEG = 0.01
# Noise is drawn in blocks of this many samples per detector, each seeded by
# (seed, detector key, block index).
_NOISE_BLOCK_SAMPLES = 4096
_MODEL_SCHEMA_VERSION_DRIVE = 2


@dataclass(frozen=True)
class DetectorLoading:
    """Optical power on detectors along a trajectory.

    Attributes
    ----------
    power : astropy.units.Quantity
        Power without noise: sources, atmosphere and instrument background,
        in pW, of shape (n_detectors, n_times).
    power_noise : astropy.units.Quantity
        Standard deviation of the white power noise per sample, in pW, of the
        same shape.
    """

    power: u.Quantity
    power_noise: u.Quantity


@dataclass(frozen=True)
class KidsSignals:
    """KIDs detector states and readout signals.

    Attributes
    ----------
    x : numpy.ndarray
        Detuning ``f_in/fr - 1`` at the probe frequency, of shape
        (n_detectors, n_times).
    r : numpy.ndarray
        Loss ``1/(2*Qr)``, of the same shape.
    iq : numpy.ndarray
        Complex readout signal in the model table's signal units, of the same
        shape.
    """

    x: np.ndarray
    r: np.ndarray
    iq: np.ndarray


def get_detector_loading(
    array_name: ArrayLike,
    alt: u.Quantity,
    surface_brightness: u.Quantity,
    loading_models: Mapping[ToltecArrayName, ToltecArrayLoadingModel],
    f_smp: u.Quantity,
) -> DetectorLoading:
    """Return the optical power on detectors along a trajectory.

    Parameters
    ----------
    array_name : array_like of str
        Array name of each detector.
    alt : astropy.units.Quantity
        Detector altitudes, of shape (n_detectors, n_times), such as
        ``DetectorPositions.coords_altaz.alt``.
    surface_brightness : astropy.units.Quantity
        Source surface brightness at the detector positions, of the shape of
        ``alt``, such as from `tolteca_simu.sources.ImageSource.evaluate`.
    loading_models : dict of ToltecArrayLoadingModel
        Loading model by array name, for the atmosphere and telescope
        conditions of the observation.
    f_smp : astropy.units.Quantity
        Sampling frequency.

    Returns
    -------
    DetectorLoading
        Power without noise and the noise standard deviation per sample.
        Values at each time depend on that time only.

    Raises
    ------
    KeyError
        A detector's array has no loading model.
    """
    array_name = np.asarray(array_name)
    alt_deg = alt.to_value(u.deg)
    surface_brightness_mjysr = surface_brightness.to_value(u.MJy / u.sr)
    power = np.empty(alt_deg.shape)
    nep = np.empty(alt_deg.shape)
    unit_brightness = 1 << u.MJy / u.sr
    for name in np.unique(array_name):
        mask = array_name == name
        model = loading_models[name]
        power_background, nep_, power_per_brightness = _interpolate_on_altitude(
            lambda a, model=model: (
                model.get_power(a << u.deg).to_value(u.pW),
                model.get_noise(a << u.deg).nep.to_value(u.pW * u.Hz**-0.5),
                model.get_source_power(unit_brightness, a << u.deg).to_value(u.pW),
            ),
            alt_deg[mask],
            model.alt_range.to_value(u.deg),
        )
        power[mask] = (
            power_background + surface_brightness_mjysr[mask] * power_per_brightness
        )
        nep[mask] = nep_
    noise_scale = np.sqrt(f_smp.to_value(u.Hz) / 2.0)
    return DetectorLoading(power=power << u.pW, power_noise=(nep * noise_scale) << u.pW)


def realize_power_noise(
    power_noise: u.Quantity,
    seed: int,
    detector_keys: ArrayLike,
    sample_start: int,
) -> u.Quantity:
    """Return a reproducible realization of white power noise.

    Parameters
    ----------
    power_noise : astropy.units.Quantity
        Standard deviation per sample, of shape (n_detectors, n_times), such as
        `DetectorLoading.power_noise`.
    seed : int
        Seed of the simulation run.
    detector_keys : array_like of int
        A non-negative key per detector that stays the same across the run,
        such as the detector's row in the array property table.
    sample_start : int
        Index of the first sample within the run.

    Returns
    -------
    astropy.units.Quantity
        Noise of the shape and unit of ``power_noise``. The same seed and keys
        give the same noise for each sample, however the run is split in time.
    """
    n_times = power_noise.shape[-1]
    block_first = sample_start // _NOISE_BLOCK_SAMPLES
    block_last = (sample_start + n_times - 1) // _NOISE_BLOCK_SAMPLES
    offset = sample_start - block_first * _NOISE_BLOCK_SAMPLES
    noise = np.empty(power_noise.shape)
    for i, key in enumerate(np.asarray(detector_keys)):
        blocks = [
            np.random.default_rng(
                np.random.SeedSequence(seed, spawn_key=(int(key), block))
            ).standard_normal(_NOISE_BLOCK_SAMPLES)
            for block in range(block_first, block_last + 1)
        ]
        noise[i] = np.concatenate(blocks)[offset : offset + n_times]
    return u.Quantity(noise * power_noise, copy=False)


def get_kids_signals(
    power: u.Quantity,
    power_ref: u.Quantity,
    responsivity: u.Quantity,
    model_params: Table,
) -> KidsSignals:
    """Return the KIDs states and readout signals for detector power.

    Each detector's resonance moves with the absorbed power, from its state in
    the model table, ``x = x_ref + responsivity * (power - power_ref)``, and is
    read out at the fixed probe frequency through the model. Inverting the
    signal with the same model table recovers ``x`` and ``r``.

    Parameters
    ----------
    power : astropy.units.Quantity
        Detector power, of shape (n_detectors, n_times).
    power_ref : astropy.units.Quantity
        Power of each detector when the model table was measured, such as at the
        tune before the observation.
    responsivity : astropy.units.Quantity
        Change of the detuning per power, one per detector.
    model_params : astropy.table.Table
        KIDs model table, one row per detector in detector order, as
        `tolteca_kidsproc.timestream.TimestreamSolver` accepts it, of a
        physical model family: ``model_schema`` ``KidsSweepWithAffineGain`` or
        ``KidsSweepWithDelayGain``. Version 2 adds the drive coefficient ``b``.
        ``f_in`` is the probe frequency.

    Returns
    -------
    KidsSignals
        Detuning, loss and readout signal.

    Raises
    ------
    ValueError
        The table is invalid or not of a physical model family, or its rows do
        not match the detectors.
    """
    model, f_in = _get_kids_model(model_params)
    if len(f_in) != power.shape[0]:
        msg = f"model_params has {len(f_in)} rows for {power.shape[0]} detectors"
        raise ValueError(msg)
    fr_ref = np.asarray(model.fr)
    x_ref = f_in / fr_ref - 1.0
    dx = (responsivity[:, np.newaxis] * (power - power_ref[:, np.newaxis])).to_value(
        u.dimensionless_unscaled
    )
    x = x_ref[:, np.newaxis] + dx
    fr = f_in[:, np.newaxis] / (1.0 + x)
    # The model broadcasts as (sample, model).
    iq = dataclasses.replace(model, fr=fr.T).eval(f_in).T
    r = np.broadcast_to(np.asarray(model.r)[:, np.newaxis], x.shape)
    return KidsSignals(x=x, r=r, iq=iq)


def _interpolate_on_altitude(
    func: Callable[[np.ndarray], tuple[np.ndarray, ...]],
    alt_deg: np.ndarray,
    alt_range_deg: np.ndarray,
) -> tuple[np.ndarray, ...]:
    # Beyond the table range the values are those at the edge. Knots stay
    # inside the range, so no stencil spans the edge.
    k_min = int(np.ceil(alt_range_deg[0] / _ALT_STEP_DEG))
    k_max = int(np.floor(alt_range_deg[1] / _ALT_STEP_DEG))
    position = np.clip(alt_deg, *alt_range_deg) / _ALT_STEP_DEG
    first = np.clip(np.floor(position).astype(int) - 1, k_min, k_max - 3)
    k_first = int(first.min())
    knots = np.arange(k_first, int(first.max()) + 4)
    values = func(knots * _ALT_STEP_DEG)
    t = position - first
    weights = (
        -(t - 1.0) * (t - 2.0) * (t - 3.0) / 6.0,
        t * (t - 2.0) * (t - 3.0) / 2.0,
        -t * (t - 1.0) * (t - 3.0) / 2.0,
        t * (t - 1.0) * (t - 2.0) / 6.0,
    )
    i = first - k_first
    return tuple(
        sum(w * np.asarray(v)[i + j] for j, w in enumerate(weights)) for v in values
    )


def _get_kids_model(
    model_params: Table,
) -> tuple[KidsSweepWithAffineGain | KidsSweepWithDelayGain, np.ndarray]:
    # TolTECA is an optional dependency of tolteca_simu.
    from tolteca_kidsproc.models import (  # noqa: PLC0415
        KidsSweepWithAffineGain,
        KidsSweepWithDelayGain,
    )
    from tolteca_kidsproc.timestream import TimestreamSolver  # noqa: PLC0415

    # The reduction's solver validates the table: schema, units and channels.
    TimestreamSolver(model_params, model_params["chan"])
    schema = model_params.meta["model_schema"]
    name, version = schema["name"], schema["version"]
    if name not in {"KidsSweepWithAffineGain", "KidsSweepWithDelayGain"}:
        msg = (
            f"Cannot simulate model_schema {name}; use KidsSweepWithAffineGain "
            "or KidsSweepWithDelayGain"
        )
        raise ValueError(msg)

    def col(c: str) -> np.ndarray:
        return np.asarray(model_params[c], float)

    r = col("r")
    values = {
        "fr": col("fr"),
        "r": r,
        "c": col("c_re") + 1j * col("c_im"),
        "f_g": col("f_g"),
        "H0": col("H0_re") + 1j * col("H0_im"),
        # Version 2 stores the drive coefficient b = 2 * a_nl * r**3.
        "a_nl": (
            col("b") / (2.0 * r**3)
            if version == _MODEL_SCHEMA_VERSION_DRIVE
            else np.zeros(len(r))
        ),
    }
    if name == "KidsSweepWithAffineGain":
        model = KidsSweepWithAffineGain(**values, H1=col("H1_re") + 1j * col("H1_im"))
    else:
        model = KidsSweepWithDelayGain(**values, a=col("a"), tau=col("tau"))
    return model, col("f_in")
