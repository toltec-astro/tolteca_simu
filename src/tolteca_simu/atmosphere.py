"""Turbulent atmosphere above the LMT along detector lines of sight.

TOAST 3 simulates the turbulent atmosphere above the telescope during an
observation, and detectors observe it along their lines of sight. This requires
the ``toast`` extra, ``tolteca_simu[toast]``.
"""

import datetime
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Self

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.table import QTable
from pydantic import ConfigDict, Field
from tollan.config import FrozenBaseModel
from tollan.config.types import AngleQuantityField, LengthQuantityField, quantity_field

from tolteca_simu.lmt import get_lmt_observer
from tolteca_simu.planning.trajectory import Trajectory

__all__ = ["SiteWeather", "ToastAtmosphere", "ToastAtmosphereConfig"]

type PressureQuantityField = quantity_field("pressure")  # ty: ignore[invalid-type-form]
type TemperatureQuantityField = quantity_field("temperature")  # ty: ignore[invalid-type-form]
type SpeedQuantityField = quantity_field("speed")  # ty: ignore[invalid-type-form]

# Fade time at wind breaks: the default of TOAST 3.0.6 SimAtmosphere.
_FADE_TIME_S = 60.0


class SiteWeather(FrozenBaseModel):
    """Weather at the telescope.

    LMT telescope files record these values in their ``Header.Weather``
    variables.
    """

    model_config = ConfigDict(extra="forbid")
    pressure: PressureQuantityField = Field(description="Atmospheric pressure.")
    air_temperature: TemperatureQuantityField = Field(description="Air temperature.")
    wind_speed: SpeedQuantityField = Field(description="Wind speed.")
    wind_direction: AngleQuantityField = Field(
        description="Direction the wind blows from, east of north."
    )


class ToastAtmosphereConfig(FrozenBaseModel):
    """Physical parameters of TOAST's atmosphere model.

    The defaults are those of TOAST 3.0.6.
    """

    model_config = ConfigDict(extra="forbid")
    gain: float = Field(
        default=1e-5,
        description="Scale of the simulated fluctuations; not yet calibrated for "
        "the LMT.",
    )
    lmin_center: LengthQuantityField = Field(
        default=0.01 << u.m, description="Center of the turbulence dissipation scale."
    )
    lmin_sigma: LengthQuantityField = Field(
        default=0.001 << u.m,
        description="Standard deviation of the turbulence dissipation scale.",
    )
    lmax_center: LengthQuantityField = Field(
        default=10.0 << u.m, description="Center of the turbulence injection scale."
    )
    lmax_sigma: LengthQuantityField = Field(
        default=10.0 << u.m,
        description="Standard deviation of the turbulence injection scale.",
    )
    z0_center: LengthQuantityField = Field(
        default=2000.0 << u.m,
        description="Center of the water vapor distribution height.",
    )
    z0_sigma: LengthQuantityField = Field(
        default=0.0 << u.m,
        description="Standard deviation of the water vapor distribution height.",
    )
    zatm: LengthQuantityField = Field(
        default=40000.0 << u.m,
        description="Height of the atmosphere for the temperature profile.",
    )
    zmax: LengthQuantityField = Field(
        default=2000.0 << u.m,
        description="Height of the simulated water vapor.",
    )


# Realizations come from generate; the constructor is not public.
class ToastAtmosphere:  # numpydoc ignore=PR01
    """A TOAST realization of the turbulent atmosphere during an observation.

    Create a realization with `generate`. TOAST divides the observation into
    wind intervals, each with its own atmosphere volume that the wind carries
    across the field.
    """

    def __init__(  # noqa: PLR0913
        self,
        *,
        weather: SiteWeather,
        config: ToastAtmosphereConfig,
        seed: int,
        time_unix: np.ndarray,
        wind_intervals: np.ndarray,
        volumes: list,
    ) -> None:
        self._weather = weather
        self._config = config
        self._seed = seed
        self._time_unix = time_unix
        self._wind_intervals = wind_intervals
        self._volumes = volumes

    @property
    def weather(self) -> SiteWeather:
        """Weather of the realization."""
        return self._weather

    @property
    def config(self) -> ToastAtmosphereConfig:
        """Atmosphere parameters of the realization."""
        return self._config

    @property
    def seed(self) -> int:
        """Seed of the realization."""
        return self._seed

    @property
    def wind_intervals(self) -> np.ndarray:
        """Wind intervals: first and end sample indices, of shape (n, 2)."""
        return self._wind_intervals

    @classmethod
    @contextmanager
    def generate(
        cls,
        trajectory: Trajectory,
        field_of_view: u.Quantity,
        weather: SiteWeather,
        config: ToastAtmosphereConfig,
        seed: int,
    ) -> Iterator[Self]:
        """Simulate the atmosphere above the LMT during an observation.

        Parameters
        ----------
        trajectory : tolteca_simu.planning.Trajectory
            The boresight trajectory. Wind intervals break in its turnarounds
            where possible.
        field_of_view : astropy.units.Quantity
            Diameter of the field around the boresight that the detectors
            observe.
        weather : SiteWeather
            Weather at the telescope.
        config : ToastAtmosphereConfig
            Parameters of the atmosphere model.
        seed : int
            Seed of the realization, from 0 to ``2**32 - 1``. The same seed,
            parameters, weather and trajectory give the same realization.

        Yields
        ------
        ToastAtmosphere
            The realization. Observe it within the context; its memory is
            released on exit.
        """
        # TOAST is an optional dependency of tolteca_simu.
        import toast  # noqa: PLC0415
        from toast import qarray  # noqa: PLC0415
        from toast.instrument import (  # noqa: PLC0415
            Focalplane,
            GroundSite,
            Session,
            Telescope,
        )
        from toast.intervals import IntervalList  # noqa: PLC0415
        from toast.observation import default_values  # noqa: PLC0415
        from toast.ops.sim_tod_atm_generate import GenerateAtmosphere  # noqa: PLC0415
        from toast.weather import Weather  # noqa: PLC0415

        time_unix = np.asarray(trajectory.time.unix, dtype=np.float64)
        n_times = time_unix.size
        start, end = (
            t.to_datetime(timezone=datetime.UTC)
            for t in (trajectory.time[0], trajectory.time[-1])
        )
        location = get_lmt_observer().location
        wind_direction = weather.wind_direction.to_value(u.rad)
        site = GroundSite(
            "LMT",
            location.lat,
            location.lon,
            location.height,
            weather=Weather(
                time=start,
                surface_pressure=weather.pressure,
                air_temperature=weather.air_temperature.to(
                    u.K, equivalencies=u.temperature()
                ),
                # TOAST's components: the eastward and northward wind.
                west_wind=-weather.wind_speed * np.sin(wind_direction),
                south_wind=-weather.wind_speed * np.cos(wind_direction),
            ),
        )
        focalplane = Focalplane(
            detector_data=QTable(
                {"name": ["boresight"], "quat": [[0.0, 0.0, 0.0, 1.0]]}
            ),
            field_of_view=field_of_view,
            sample_rate=(n_times - 1) / (time_unix[-1] - time_unix[0]) << u.Hz,
        )
        comm = toast.Comm()
        data = toast.Data(comm)
        observation = toast.Observation(
            comm,
            Telescope("LMT", focalplane=focalplane, site=site),
            n_samples=n_times,
            name="observation",
            session=Session("observation", uid=seed, start=start, end=end),
        )
        shared = observation.shared
        shared.create_column(default_values.times, shape=(n_times,), dtype=np.float64)
        shared[default_values.times].set(time_unix, offset=(0,), fromrank=0)
        altaz = trajectory.coords_altaz
        # TOAST's horizon longitude is the negative azimuth.
        shared.create_column(
            default_values.boresight_azel, shape=(n_times, 4), dtype=np.float64
        )
        shared[default_values.boresight_azel].set(
            qarray.from_lonlat_angles(
                -altaz.az.radian, altaz.alt.radian, np.zeros(n_times)
            ),
            offset=(0, 0),
            fromrank=0,
        )
        observation.intervals["turnaround"] = IntervalList(
            time_unix, samplespans=_get_true_spans(trajectory.turnaround)
        )
        data.obs.append(observation)
        GenerateAtmosphere(
            times=default_values.times,
            boresight=default_values.boresight_azel,
            shared_flags=None,
            turnaround_interval="turnaround",
            wind_intervals="wind",
            output="atmosphere",
            lmin_center=config.lmin_center,
            lmin_sigma=config.lmin_sigma,
            lmax_center=config.lmax_center,
            lmax_sigma=config.lmax_sigma,
            z0_center=config.z0_center,
            z0_sigma=config.z0_sigma,
            zatm=config.zatm,
            zmax=config.zmax,
        ).apply(data)
        volumes = data["atmosphere"]["observation"]
        wind_intervals = np.array(
            [(i.first, i.last) for i in observation.intervals["wind"]], dtype=int
        )
        try:
            yield cls(
                weather=weather,
                config=config,
                seed=seed,
                time_unix=time_unix,
                wind_intervals=wind_intervals,
                volumes=volumes,
            )
        finally:
            for cones in volumes:
                for cone in cones:
                    cone.close()
            data.clear()

    def observe(self, coords_altaz: SkyCoord) -> np.ndarray:
        """Return the atmosphere integrated along detector lines of sight.

        Parameters
        ----------
        coords_altaz : astropy.coordinates.SkyCoord
            Detector positions in horizon coordinates, of shape
            (n_detectors, n_times), at all times of the trajectory, such as
            `tolteca_simu.toltec.DetectorPositions.coords_altaz`.

        Returns
        -------
        numpy.ndarray
            TOAST's line-of-sight integral, of shape (n_detectors, n_times).
            The mean of each wind interval is removed, then the values fade to
            zero over 60 s on both sides of each wind break. The integral times
            the gain and the atmosphere absorption coefficient is a brightness
            temperature in K. Values of a detector depend on its positions
            only.

        Raises
        ------
        ValueError
            The positions are not at the times of the trajectory, or lie
            outside the field of view of the realization.
        """
        az = np.atleast_2d(coords_altaz.az.radian)
        alt = np.atleast_2d(coords_altaz.alt.radian)
        n_times = self._time_unix.size
        if az.shape[-1] != n_times:
            msg = f"coords_altaz has {az.shape[-1]} times, the trajectory {n_times}"
            raise ValueError(msg)
        n_wind = len(self._wind_intervals)
        data = np.zeros(az.shape)
        for i_wind, ((first, end), cones) in enumerate(
            zip(self._wind_intervals, self._volumes, strict=True)
        ):
            time_unix = self._time_unix[first:end]
            # All cones of a wind interval span the same horizon range.
            az_min = cones[0].azmin
            az_wind = az_min + np.mod(az[:, first:end] - az_min, 2 * np.pi)
            alt_wind = alt[:, first:end]
            if (
                az_wind.max() > cones[0].azmax
                or alt_wind.min() < cones[0].elmin
                or alt_wind.max() > cones[0].elmax
            ):
                msg = "Detector positions lie outside the field of view"
                raise ValueError(msg)
            n_fade = _get_n_fade(time_unix)
            for i_det in range(az.shape[0]):
                tod = np.zeros(end - first)
                for cone in cones:
                    # Each cone adds its part of the line of sight to tod.
                    status = cone.observe(
                        time_unix, az_wind[i_det], alt_wind[i_det], tod, -1.0
                    )
                    if status != 0:
                        msg = "Detector positions lie outside the field of view"
                        raise ValueError(msg)
                tod -= tod.mean()
                if n_fade > 0:
                    if i_wind < n_wind - 1:
                        tod[-n_fade:] *= np.arange(n_fade - 1, -1, -1) / n_fade
                    if i_wind > 0:
                        tod[:n_fade] *= np.arange(n_fade) / n_fade
                data[i_det, first:end] = tod
        return data


def _get_true_spans(mask: np.ndarray) -> list[tuple[int, int]]:
    # First and end indices of each run of True values.
    edges = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return list(
        zip(
            np.flatnonzero(edges == 1).tolist(),
            np.flatnonzero(edges == -1).tolist(),
            strict=True,
        )
    )


def _get_n_fade(time_unix: np.ndarray) -> int:
    # TOAST's fade length: fade time at the mean sampling rate, at most half
    # the wind interval.
    n = time_unix.size
    if n < 2:  # noqa: PLR2004
        return 0
    f_smp = (n - 1) / (time_unix[-1] - time_unix[0])
    return min(int(_FADE_TIME_S * f_smp), n // 2)
