from pathlib import Path

import astropy.units as u
import numpy as np
import pytest
from astropy.constants import codata2018 as const
from astropy.coordinates import SkyCoord
from astropy.table import QTable
from astropy.time import Time
from tollan.config import RuntimeContext

from tolteca_simu.atmosphere import SiteWeather, ToastAtmosphere, ToastAtmosphereConfig
from tolteca_simu.core import Simu
from tolteca_simu.lmt import LmtAtmModelName, get_lmt_observer
from tolteca_simu.mapping import RasterPattern
from tolteca_simu.planning.trajectory import Trajectory, get_trajectory
from tolteca_simu.toltec import get_detector_positions
from tolteca_simu.toltec.atmosphere import AtmospherePower, get_matched_pwv

toast = pytest.importorskip("toast")

# The summit weather of telescope file 145480 (2025-10-31, Header.Weather).
SUMMIT = {
    "pressure": "0.5904 bar",
    "air_temperature": "0.3 deg_C",
    "wind_direction": "319.2 deg",
}
# A water vapor height of 200 m keeps the simulated volume small and the tests
# fast; the properties tested do not depend on it.
CONFIG = ToastAtmosphereConfig(zmax=200 << u.m)
FIELD_OF_VIEW = 4.5 << u.arcmin
# Detector offsets within the TolTEC field of view.
X_T = [0.0, 1.5, -1.0, 0.3, 2.0] << u.arcmin
Y_T = [0.0, 0.5, 1.2, -1.8, 0.0] << u.arcmin
# The aatm/am power ratio of each array at the matched PWV is within 1.8 % of
# one (measured 2026-11-14, python/run/simu-toast-atmosphere-20261114).
MATCH_RTOL = 0.02


def _weather(wind_speed: u.Quantity) -> SiteWeather:
    return SiteWeather.model_validate({**SUMMIT, "wind_speed": wind_speed})


def _raster_trajectory(t_exp: u.Quantity) -> Trajectory:
    # Scans of 8 s joined by turnarounds of 4 s.
    pattern = RasterPattern(
        length=4 << u.arcmin,
        space=0.5 << u.arcmin,
        n_scans=40,
        rot=0 << u.deg,
        speed=0.5 << u.arcmin / u.s,
        t_turnaround=4 << u.s,
    )
    return get_trajectory(
        pattern,
        SkyCoord(180 << u.deg, 20 << u.deg),
        Time("2026-03-01T06:00:00"),
        t_exp=t_exp,
        ref_frame="altaz",
        observer=get_lmt_observer(),
        f_smp=20 << u.Hz,
    )


@pytest.fixture(scope="module")
def trajectory() -> Trajectory:
    return _raster_trajectory(60 << u.s)


@pytest.fixture(scope="module")
def loading_models(cal_data_path: Path) -> dict:
    simu = Simu(
        RuntimeContext({"simu": {"obs_planner": {"cal_data_path": cal_data_path}}})
    )
    return simu.make_toltec_planner().get_loading_models("am_q50")


def test_config_defaults_are_toasts() -> None:
    sim = toast.ops.SimAtmosphere()
    for name, value in ToastAtmosphereConfig():
        assert value == getattr(sim, name), name


@pytest.mark.parametrize("atm_model_name", ["am_q25", "am_q50", "am_q75"])
def test_matched_pwv_reproduces_the_atmosphere_model_in_each_array(
    cal_data_path: Path, atm_model_name: LmtAtmModelName
) -> None:
    simu = Simu(
        RuntimeContext({"simu": {"obs_planner": {"cal_data_path": cal_data_path}}})
    )
    models = simu.make_toltec_planner().get_loading_models(atm_model_name)
    weather = _weather(5 << u.m / u.s)
    pwv = get_matched_pwv(models, weather)
    height = get_lmt_observer().location.height.to_value(u.m)
    for model in models.values():
        alt = model.alt_range[1]
        f = model.f_passband.to_value(u.GHz)
        f_band = np.linspace(f[0], f[-1], 100)
        zenith = toast.atm.atm_atmospheric_loading_vec(
            height, 273.45, 59040.0, pwv.to_value(u.mm), f_band[0], f_band[-1], 100
        )
        brightness = np.interp(f, f_band, zenith) / np.sin(alt.to_value(u.rad)) << u.K
        np.testing.assert_allclose(
            model.get_atmosphere_power(brightness),
            model.get_atmosphere_power(model.get_atmosphere_brightness(alt)),
            rtol=MATCH_RTOL,
        )


def test_power_is_the_atmosphere_term_of_the_toast_brightness(
    cal_data_path: Path, loading_models: dict, trajectory: Trajectory
) -> None:
    with ToastAtmosphere.generate(
        trajectory, FIELD_OF_VIEW, _weather(5 << u.m / u.s), CONFIG, seed=1
    ) as atmosphere:
        power = AtmospherePower.from_atmosphere(atmosphere, loading_models)
        raw = atmosphere.observe(trajectory.coords_altaz.reshape(1, -1))
    passband = QTable.read(cal_data_path / "toltec/passband/a1100_passband.ecsv")
    f = passband["f"].to_value(u.GHz)
    f_band = np.linspace(f[0], f[-1], 100)
    absorption = np.interp(
        f,
        f_band,
        toast.atm.atm_absorption_coefficient_vec(
            4640.0, 273.45, 59040.0, power.pwv.to_value(u.mm), f[0], f[-1], 100
        ),
    )
    # Detector optical efficiency 0.8 times horn aperture efficiency 0.35.
    expected = (
        const.k_B
        * (CONFIG.gain << u.K)
        * np.sum(absorption * 0.8 * 0.35 * passband["throughput"])
        * (passband["f"][1] - passband["f"][0])
    )
    np.testing.assert_allclose(power.power_scale["a1100"], expected, rtol=1e-12)
    np.testing.assert_array_equal(
        power.evaluate(["a1100", "a2000"], np.vstack([raw, raw])),
        np.vstack([raw * power.power_scale["a1100"], raw * power.power_scale["a2000"]]),
    )


def test_one_wind_interval_has_zero_mean(trajectory: Trajectory) -> None:
    positions = get_detector_positions(X_T, Y_T, trajectory)
    with ToastAtmosphere.generate(
        trajectory, FIELD_OF_VIEW, _weather(5 << u.m / u.s), CONFIG, seed=1
    ) as atmosphere:
        raw = atmosphere.observe(positions.coords_altaz)
        assert atmosphere.wind_intervals.tolist() == [[0, trajectory.t.size]]
    np.testing.assert_allclose(raw.mean(axis=1), 0, atol=1e-12 * raw.std())


def test_wind_breaks_fall_in_turnarounds_and_fade_to_zero() -> None:
    # At 60 m/s the volume lasts 50 s, which ends within a scan; the interval
    # extends to the next turnaround, to the whole second.
    trajectory = _raster_trajectory(90 << u.s)
    positions = get_detector_positions(X_T, Y_T, trajectory)
    with ToastAtmosphere.generate(
        trajectory, FIELD_OF_VIEW, _weather(60 << u.m / u.s), CONFIG, seed=1
    ) as atmosphere:
        raw = atmosphere.observe(positions.coords_altaz)
        wind_intervals = atmosphere.wind_intervals
    assert len(wind_intervals) > 1
    n_per_s = 20
    for first, _ in wind_intervals[1:]:
        assert trajectory.turnaround[first - n_per_s : first + 1].any()
        np.testing.assert_array_equal(raw[:, first - 1 : first + 1], 0.0)
    assert np.all(raw.std(axis=1) > 0)


def test_detector_groups_and_seeds_give_reproducible_values(
    trajectory: Trajectory,
) -> None:
    positions = get_detector_positions(X_T, Y_T, trajectory)
    weather = _weather(5 << u.m / u.s)
    with ToastAtmosphere.generate(
        trajectory, FIELD_OF_VIEW, weather, CONFIG, seed=1
    ) as atmosphere:
        raw = atmosphere.observe(positions.coords_altaz)
        groups = [
            atmosphere.observe(positions.coords_altaz[i]) for i in [[3, 1], [4, 0, 2]]
        ]
    raw_groups = np.empty_like(raw)
    raw_groups[[3, 1]] = groups[0]
    raw_groups[[4, 0, 2]] = groups[1]
    np.testing.assert_array_equal(raw_groups, raw)
    with ToastAtmosphere.generate(
        trajectory, FIELD_OF_VIEW, weather, CONFIG, seed=1
    ) as atmosphere:
        np.testing.assert_array_equal(atmosphere.observe(positions.coords_altaz), raw)
    with ToastAtmosphere.generate(
        trajectory, FIELD_OF_VIEW, weather, CONFIG, seed=2
    ) as atmosphere:
        assert not np.allclose(atmosphere.observe(positions.coords_altaz), raw)


def test_observe_equals_toasts_simatmosphere() -> None:
    # TOAST's own simulation of one boresight detector with a top-hat band, at
    # the same times, pointing, weather and seed, in K_CMB.
    trajectory = _raster_trajectory(90 << u.s)
    weather = _weather(60 << u.m / u.s)
    seed = 7
    times = trajectory.time.unix
    n = times.size
    az = trajectory.coords_altaz.az.radian
    alt = trajectory.coords_altaz.alt.radian
    with ToastAtmosphere.generate(
        trajectory, FIELD_OF_VIEW, weather, CONFIG, seed=seed
    ) as atmosphere:
        raw = atmosphere.observe(trajectory.coords_altaz.reshape(1, -1))[0]
    location = get_lmt_observer().location
    direction = weather.wind_direction.to_value(u.rad)
    site = toast.instrument.GroundSite(
        "LMT",
        location.lat,
        location.lon,
        location.height,
        weather=toast.weather.Weather(
            time=trajectory.time[0].to_datetime(),
            pwv=1.0 << u.mm,
            surface_pressure=weather.pressure,
            air_temperature=273.45 << u.K,
            west_wind=-weather.wind_speed * np.sin(direction),
            south_wind=-weather.wind_speed * np.cos(direction),
        ),
    )
    focalplane = toast.instrument.Focalplane(
        detector_data=QTable(
            {
                "name": ["d0"],
                "quat": [[0.0, 0.0, 0.0, 1.0]],
                "bandcenter": [273.0] << u.GHz,
                "bandwidth": [40.0] << u.GHz,
            }
        ),
        field_of_view=FIELD_OF_VIEW,
        sample_rate=20 << u.Hz,
    )
    comm = toast.Comm()
    data = toast.Data(comm)
    defaults = toast.observation.default_values
    obs = toast.Observation(
        comm,
        toast.instrument.Telescope("LMT", focalplane=focalplane, site=site),
        n_samples=n,
        name="observation",
        session=toast.instrument.Session("observation", uid=seed),
    )
    obs.shared.create_column(defaults.times, shape=(n,), dtype=np.float64)
    obs.shared[defaults.times].set(times, offset=(0,), fromrank=0)
    obs.shared.create_column(defaults.boresight_azel, shape=(n, 4), dtype=np.float64)
    obs.shared[defaults.boresight_azel].set(
        toast.qarray.from_lonlat_angles(-az, alt, np.zeros(n)),
        offset=(0, 0),
        fromrank=0,
    )
    obs.shared.create_column(defaults.shared_flags, shape=(n,), dtype=np.uint8)
    obs.detdata.create(defaults.det_flags, dtype=np.uint8)
    edges = np.diff(np.concatenate([[0], trajectory.turnaround.astype(int), [0]]))
    obs.intervals["turnaround"] = toast.intervals.IntervalList(
        times,
        samplespans=list(
            zip(
                np.flatnonzero(edges == 1).tolist(),
                np.flatnonzero(edges == -1).tolist(),
                strict=True,
            )
        ),
    )
    data.obs.append(obs)
    toast.ops.SimAtmosphere(
        detector_pointing=toast.ops.PointingDetectorSimple(
            boresight=defaults.boresight_azel, quats="quats_azel"
        ),
        det_data="atm",
        add_loading=False,
        gain=CONFIG.gain,
        zmax=CONFIG.zmax,
    ).apply(data)
    expected = np.asarray(obs.detdata["atm"][0, :])
    bandpass = obs.telescope.focalplane.bandpass
    f_min, f_max = bandpass.get_range(det="d0")
    f_band = np.linspace(f_min, f_max, 100)
    absorption = bandpass.convolve(
        "d0",
        f_band,
        toast.atm.atm_absorption_coefficient_vec(
            location.height.to_value(u.m),
            273.45,
            59040.0,
            1.0,
            f_band[0].to_value(u.GHz),
            f_band[-1].to_value(u.GHz),
            100,
        ),
        rj=True,
    )
    np.testing.assert_allclose(
        raw * CONFIG.gain * absorption, expected, rtol=0, atol=1e-12 * expected.std()
    )


def test_positions_outside_the_field_or_the_trajectory_raise(
    trajectory: Trajectory,
) -> None:
    with ToastAtmosphere.generate(
        trajectory, FIELD_OF_VIEW, _weather(5 << u.m / u.s), CONFIG, seed=1
    ) as atmosphere:
        far = get_detector_positions([10.0] << u.arcmin, [0.0] << u.arcmin, trajectory)
        with pytest.raises(ValueError, match="outside the field of view"):
            atmosphere.observe(far.coords_altaz)
        with pytest.raises(ValueError, match="times"):
            atmosphere.observe(trajectory.coords_altaz[:-1].reshape(1, -1))
