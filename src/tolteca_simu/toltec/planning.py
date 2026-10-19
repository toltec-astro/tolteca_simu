"""TolTEC planning results for an observation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import astropy.units as u
import numpy as np

from tolteca_simu.mapping import RasterPattern

from .coverage import (
    CoverageMap,
    Footprint,
    get_array_outline,
    get_coverage_map,
    get_footprint,
    place_on_sky,
)
from .info import TOLTEC_ARRAYS, ToltecArrayName
from .sensitivity import (
    POLARIZED_NOISE_FACTOR,
    ArrayNoise,
    MapDepth,
    ToltecArrayLoadingModel,
    get_map_depth,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from astroplan import Observer
    from astropy.coordinates import SkyCoord
    from astropy.table import QTable

    from tolteca_simu.cal_data import CalDataStore
    from tolteca_simu.lmt import LmtAtmModelName
    from tolteca_simu.mapping import MappingPattern
    from tolteca_simu.planning import ObservationDescription, Trajectory

__all__ = [
    "ToltecArraySummary",
    "ToltecPlanner",
    "ToltecPlanningResult",
    "get_toltec_planning_result",
]


@dataclass(frozen=True)
class ToltecArraySummary:
    """Sensitivity of one array for an observation.

    Attributes
    ----------
    array_name : str
        Array name.
    n_dets, n_dets_designed : int
        Enabled and designed detector counts.
    alt_mean : astropy.units.Quantity
        Mean target altitude during the observation.
    power : astropy.units.Quantity
        Detector power loading at ``alt_mean``.
    noise : tolteca_simu.toltec.ArrayNoise
        Detector noise at ``alt_mean``.
    nefd : astropy.units.Quantity
        NEFD for the measured Stokes parameters.
    detector_sensitivity : astropy.units.Quantity
        ``sqrt(2) * nefd``, in mJy s^1/2.
    mapping_speed : astropy.units.Quantity
        Mapping speed for the measured Stokes parameters.
    depth_rms : astropy.units.Quantity
        Median map depth for one pass.
    depth_rms_coadd : astropy.units.Quantity
        Median map depth after all passes.
    """

    array_name: ToltecArrayName
    n_dets: int
    n_dets_designed: int
    alt_mean: u.Quantity
    power: u.Quantity
    noise: ArrayNoise
    nefd: u.Quantity
    detector_sensitivity: u.Quantity
    mapping_speed: u.Quantity
    depth_rms: u.Quantity
    depth_rms_coadd: u.Quantity


@dataclass(frozen=True)
class ToltecPlanningResult:
    """TolTEC coverage and sensitivity of an observation.

    Attributes
    ----------
    array_name : str
        The array whose coverage was computed.
    polarized : bool
        Whether depths are for polarized intensity (Stokes Q/U).
    footprint : tolteca_simu.toltec.Footprint
        The array's detectors on the sky.
    fov_outline : astropy.coordinates.SkyCoord
        Outline of the designed array, placed on the sky as the footprint.
    coverage : tolteca_simu.toltec.CoverageMap
        Coverage of the array, in seconds per pixel.
    depth : tolteca_simu.toltec.MapDepth
        Depth of the array's map.
    t_exp : astropy.units.Quantity
        Time per pass.
    t_exp_eff : astropy.units.Quantity
        On-target time per pass: for a raster, without the turnarounds.
    n_passes : int
        Passes needed for the desired depth on the array.
    desired_sens : astropy.units.Quantity
        The desired coadded depth.
    summaries : dict of ToltecArraySummary
        Sensitivity of every array, keyed by name; other arrays' depths scale
        from the computed array's by their NEFD.
    """

    array_name: ToltecArrayName
    polarized: bool
    footprint: Footprint
    fov_outline: SkyCoord
    coverage: CoverageMap
    depth: MapDepth
    t_exp: u.Quantity
    t_exp_eff: u.Quantity
    n_passes: int
    desired_sens: u.Quantity
    summaries: dict[ToltecArrayName, ToltecArraySummary]


def get_toltec_planning_result(  # noqa: PLR0913
    *,
    pattern: MappingPattern,
    trajectory: Trajectory,
    target: SkyCoord,
    observer: Observer,
    t_exp: u.Quantity,
    apt: QTable,
    n_dets_designed: dict[ToltecArrayName, int],
    array_outline: tuple[u.Quantity, u.Quantity],
    loading_models: dict[ToltecArrayName, ToltecArrayLoadingModel],
    array_name: ToltecArrayName,
    polarized: bool,
    desired_sens: u.Quantity,
) -> ToltecPlanningResult:
    """Compute TolTEC coverage and sensitivity for an observation.

    Loading and noise are evaluated at the mean target altitude. The selected
    array's map depth sets the number of passes for the desired depth.

    Parameters
    ----------
    pattern : tolteca_simu.mapping.MappingPattern
        The mapping pattern.
    trajectory : tolteca_simu.planning.Trajectory
        The boresight trajectory of one pass.
    target : astropy.coordinates.SkyCoord
        The target.
    observer : astroplan.Observer
        The observing site.
    t_exp : astropy.units.Quantity
        Time per pass.
    apt : astropy.table.QTable
        Array property table of the enabled detectors.
    n_dets_designed : dict of int
        Designed detector count of each array.
    array_outline : tuple of astropy.units.Quantity
        Outline of the designed array as offsets from the boresight, from
        `tolteca_simu.toltec.get_array_outline`.
    loading_models : dict of ToltecArrayLoadingModel
        Loading model of each array, for the observing conditions.
    array_name : str
        Array whose coverage and depth are computed.
    polarized : bool
        Whether to report polarized-intensity sensitivity.
    desired_sens : astropy.units.Quantity
        Desired coadded map depth.

    Returns
    -------
    ToltecPlanningResult
        Coverage, depth, passes, and per-array sensitivity.
    """
    array = TOLTEC_ARRAYS[array_name]
    footprint = get_footprint(apt, array, trajectory, target, observer)
    fov_outline = place_on_sky(*array_outline, trajectory, target, observer)
    coverage = get_coverage_map(trajectory, footprint, array)
    alt_mean = trajectory.target_altaz.alt.mean()
    if isinstance(pattern, RasterPattern):
        t_exp_eff = t_exp - pattern.t_turnaround * (pattern.n_scans - 1)
    else:
        t_exp_eff = t_exp
    noise_factor = POLARIZED_NOISE_FACTOR if polarized else 1.0
    noises = {name: m.get_noise(alt_mean) for name, m in loading_models.items()}
    nefds = {name: noise.nefd * noise_factor for name, noise in noises.items()}
    depth = get_map_depth(coverage, nefds[array_name], array)
    n_passes = int(np.ceil((depth.depth_rms / desired_sens) ** 2))
    summaries = {}
    array_index = np.asarray(apt["array"])
    for name, model in loading_models.items():
        n_dets = int((array_index == TOLTEC_ARRAYS[name].index).sum())
        depth_rms = depth.depth_rms / nefds[array_name] * nefds[name]
        summaries[name] = ToltecArraySummary(
            array_name=name,
            n_dets=n_dets,
            n_dets_designed=n_dets_designed[name],
            alt_mean=alt_mean,
            power=model.get_power(alt_mean),
            noise=noises[name],
            nefd=nefds[name],
            detector_sensitivity=np.sqrt(2.0) * nefds[name].to(u.mJy * u.s**0.5),
            mapping_speed=model.get_mapping_speed(alt_mean, n_dets) / noise_factor**2,
            depth_rms=depth_rms,
            depth_rms_coadd=depth_rms / n_passes**0.5,
        )
    return ToltecPlanningResult(
        array_name=array_name,
        polarized=polarized,
        footprint=footprint,
        fov_outline=fov_outline,
        coverage=coverage,
        depth=depth,
        t_exp=t_exp,
        t_exp_eff=t_exp_eff,
        n_passes=n_passes,
        desired_sens=desired_sens,
        summaries=summaries,
    )


class ToltecPlanner:
    """TolTEC planning with fixed calibration inputs and settings.

    Loading models are built for each atmosphere model when first used and
    kept for later observations.

    Parameters
    ----------
    store : tolteca_simu.cal_data.CalDataStore
        Calibration data store.
    apt_path : str
        Array property table of the enabled detectors, relative to the store.
    tel_surface_rms : astropy.units.Quantity
        RMS of the LMT primary surface.
    det_noise_factors : dict
        Detector noise factor by atmosphere model name and array name.
    """

    def __init__(
        self,
        store: CalDataStore,
        apt_path: str,
        tel_surface_rms: u.Quantity,
        det_noise_factors: Mapping[LmtAtmModelName, Mapping[ToltecArrayName, float]],
    ) -> None:
        self._store = store
        self.apt = store.get_toltec_apt(apt_path)
        apts_designed = {
            name: store.get_toltec_apt_designed(name) for name in TOLTEC_ARRAYS
        }
        self.n_dets_designed = {name: len(t) for name, t in apts_designed.items()}
        self.array_outlines = {
            name: get_array_outline(apts_designed[name], array)
            for name, array in TOLTEC_ARRAYS.items()
        }
        self.tel_surface_rms = tel_surface_rms
        self.det_noise_factors = det_noise_factors
        self._loading_models: dict[
            str, dict[ToltecArrayName, ToltecArrayLoadingModel]
        ] = {}

    def get_loading_models(
        self, atm_model_name: LmtAtmModelName
    ) -> dict[ToltecArrayName, ToltecArrayLoadingModel]:
        """Return the loading model of each array for an atmosphere model.

        Parameters
        ----------
        atm_model_name : str
            LMT am atmosphere model name, such as ``"am_q25"``.

        Returns
        -------
        dict of ToltecArrayLoadingModel
            Models keyed by array name.
        """
        if atm_model_name not in self._loading_models:
            atm_table = self._store.get_lmt_atm_table(atm_model_name)
            self._loading_models[atm_model_name] = {
                name: ToltecArrayLoadingModel(
                    array,
                    self._store.get_toltec_passband(name),
                    atm_table,
                    tel_surface_rms=self.tel_surface_rms,
                    det_noise_factor=self.det_noise_factors[atm_model_name][name],
                )
                for name, array in TOLTEC_ARRAYS.items()
            }
        return self._loading_models[atm_model_name]

    def plan(
        self,
        description: ObservationDescription,
        trajectory: Trajectory,
        observer: Observer,
    ) -> ToltecPlanningResult:
        """Compute TolTEC coverage and sensitivity for a description.

        Parameters
        ----------
        description : tolteca_simu.planning.ObservationDescription
            The observation, with TolTEC instrument settings.
        trajectory : tolteca_simu.planning.Trajectory
            Its boresight trajectory.
        observer : astroplan.Observer
            The observing site.

        Returns
        -------
        ToltecPlanningResult
            Coverage, depth, passes, and per-array sensitivity.
        """
        instrument = description.instrument
        return get_toltec_planning_result(
            pattern=description.mapping,
            trajectory=trajectory,
            target=description.target,
            observer=observer,
            t_exp=description.get_t_exp(),
            apt=self.apt,
            n_dets_designed=self.n_dets_designed,
            array_outline=self.array_outlines[instrument.array_name],
            loading_models=self.get_loading_models(description.atm_model_name),
            array_name=instrument.array_name,
            polarized=instrument.polarized,
            desired_sens=description.desired_sens,
        )
