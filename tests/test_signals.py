import json
from pathlib import Path

import astropy.units as u
import numpy as np
import pytest
from astropy.constants import codata2018 as const
from astropy.table import QTable, Table

from tolteca_simu.cal_data import CalDataStore
from tolteca_simu.toltec import (
    TOLTEC_ARRAYS,
    get_detector_loading,
    get_kids_signals,
    realize_power_noise,
)
from tolteca_simu.toltec.sensitivity import ToltecArrayLoadingModel

DATA = Path(__file__).parent / "data"
REFERENCE = json.loads((DATA / "v1_detector_loading_reference.json").read_text())
# The loading model equals v1 to 1e-14 relative; the altitude interpolation of
# get_detector_loading differs from exact evaluation by at most 4e-13
# (measured 2026-11-13).
LOADING_RTOL = 1e-12
# v1's internal efficiencies (ToltecArrayPowerLoadingModel): detector optical
# efficiency times horn aperture efficiency.
V1_COLD_EFFICIENCY = 0.8 * 0.35
PHYSICAL_SCHEMAS = [
    ("KidsSweepWithAffineGain", 1),
    ("KidsSweepWithDelayGain", 1),
    ("KidsSweepWithAffineGain", 2),
    ("KidsSweepWithDelayGain", 2),
]
_PARAMETER_UNITS = {
    "fr": "Hz",
    "f_g": "Hz",
    "H1_re": "1 / Hz",
    "H1_im": "1 / Hz",
    "a": "1 / Hz",
    "tau": "s",
}


@pytest.fixture(scope="module")
def store(cal_data_path: Path) -> CalDataStore:
    return CalDataStore(cal_data_path)


def _loading_models(store: CalDataStore, atm_model_name: str) -> dict:
    return {
        name: ToltecArrayLoadingModel(
            array,
            store.get_toltec_passband(name),
            store.get_lmt_atm_table(atm_model_name),
            tel_surface_rms=REFERENCE["tel_surface_rms_um"] << u.um,
            det_noise_factor=REFERENCE["det_noise_factor"],
        )
        for name, array in TOLTEC_ARRAYS.items()
    }


@pytest.mark.parametrize(
    "atm_model_name", sorted({c["atm_model_name"] for c in REFERENCE["cases"]})
)
def test_background_power_and_noise_equal_v1(
    store: CalDataStore, atm_model_name: str
) -> None:
    models = _loading_models(store, atm_model_name)
    f_smp = REFERENCE["f_smp_Hz"] << u.Hz
    for case in REFERENCE["cases"]:
        if case["atm_model_name"] != atm_model_name:
            continue
        for alt, power, power_noise in zip(
            REFERENCE["alt_deg"],
            case["power_pW"],
            case["power_noise_pW"],
            strict=True,
        ):
            loading = get_detector_loading(
                [case["array_name"]],
                np.full((1, 1), alt) << u.deg,
                np.zeros((1, 1)) << u.MJy / u.sr,
                models,
                f_smp,
            )
            assert loading.power.to_value(u.pW).item() == pytest.approx(
                power, rel=LOADING_RTOL
            )
            assert loading.power_noise.to_value(u.pW).item() == pytest.approx(
                power_noise, rel=LOADING_RTOL
            )


def test_source_power_in_a_narrow_band_is_v1s_conversion(store: CalDataStore) -> None:
    # v1 converts surface brightness to its Rayleigh-Jeans temperature at the
    # band center, times k_B, the band width and the system efficiency
    # (sky_sb_to_pwr). A one-bin passband under a transparent atmosphere gives
    # the same power.
    array = TOLTEC_ARRAYS["a1100"]
    f_center = (const.c / array.wl_center).to(u.GHz)
    df = 0.01 << u.GHz
    passband = QTable(
        {"f": f_center + np.array([-1, 0, 1]) * df, "throughput": [0.0, 1.0, 0.0]}
    )
    atm_table = store.get_lmt_atm_table("am_q50")
    transparent = {**atm_table, "atmTtx": np.ones_like(atm_table["atmTtx"])}
    tel_surface_rms = 76 << u.um
    model = ToltecArrayLoadingModel(
        array, passband, transparent, tel_surface_rms, det_noise_factor=0.5
    )
    surface_brightness = 3.0 << u.MJy / u.sr
    ruze = np.exp(-(((4 * np.pi * tel_surface_rms) / array.wl_center) ** 2))
    expected = (
        surface_brightness.to(
            u.K, equivalencies=u.brightness_temperature(array.wl_center)
        )
        * const.k_B
        * df
        * ruze
        * V1_COLD_EFFICIENCY
    )
    power = model.get_source_power(surface_brightness, 45 << u.deg)
    assert power.to_value(u.pW) == pytest.approx(expected.to_value(u.pW), rel=1e-12)


def test_source_power_adds_to_the_background(store: CalDataStore) -> None:
    models = _loading_models(store, "am_q50")
    alt = np.linspace(40.0, 40.5, 6).reshape(2, 3) << u.deg
    surface_brightness = np.array([[0.0, 1.0, 2.0], [4.0, 0.0, 8.0]]) << u.MJy / u.sr
    f_smp = 122 << u.Hz
    names = ["a1100", "a2000"]
    loading = get_detector_loading(names, alt, surface_brightness, models, f_smp)
    background = get_detector_loading(names, alt, 0 * surface_brightness, models, f_smp)
    for i, name in enumerate(names):
        expected = models[name].get_source_power(
            surface_brightness[i], alt[i]
        ) + models[name].get_power(alt[i])
        np.testing.assert_allclose(
            loading.power[i].to_value(u.pW), expected.to_value(u.pW), rtol=LOADING_RTOL
        )
    # Sources add power, not noise.
    np.testing.assert_array_equal(loading.power_noise, background.power_noise)


def test_noise_is_reproducible_and_does_not_depend_on_the_split() -> None:
    # Spec: random realizations are reproducible from recorded seeds, and
    # splitting the evaluation in time does not change the result.
    sigma = np.full((3, 10000), 2.0) << u.aW
    keys = [0, 7, 3552]
    whole = realize_power_noise(sigma, seed=1, detector_keys=keys, sample_start=100)
    n = 4321
    parts = [
        realize_power_noise(sigma[:, :n], seed=1, detector_keys=keys, sample_start=100),
        realize_power_noise(
            sigma[:, n:], seed=1, detector_keys=keys, sample_start=100 + n
        ),
    ]
    np.testing.assert_array_equal(np.hstack(parts), whole)
    np.testing.assert_array_equal(
        realize_power_noise(sigma, seed=1, detector_keys=keys, sample_start=100), whole
    )
    other = realize_power_noise(sigma, seed=2, detector_keys=keys, sample_start=100)
    assert not np.any(other == whole)
    # Each detector has its own realization.
    assert not np.any(whole[0] == whole[1])


def test_noise_has_the_given_standard_deviation() -> None:
    n = 200_000
    sigma = np.full((1, n), 5.0) << u.aW
    noise = realize_power_noise(sigma, seed=3, detector_keys=[11], sample_start=0)
    assert noise.unit == u.aW
    # The standard error of the sample standard deviation is sigma/sqrt(2n).
    assert np.std(noise.value) == pytest.approx(5.0, rel=5 / np.sqrt(2 * n))
    assert np.mean(noise.value) == pytest.approx(0.0, abs=5 * 5.0 / np.sqrt(n))


def _model_table(name: str, version: int, n: int) -> Table:
    rng = np.random.default_rng(5)
    fr = rng.uniform(500e6, 700e6, n)
    r = 0.5 / rng.uniform(1e4, 3e4, n)
    qc = rng.uniform(1.5e4, 4e4, n)
    asymmetry = rng.uniform(-0.2, 0.2, n)
    h0 = 1e4 * np.exp(1j * rng.uniform(0, 2 * np.pi, n))
    columns = {
        "chan": np.arange(n),
        "f_in": fr * (1 + rng.uniform(-1.0, 1.0, n) * r),
        "f_g": fr,
        "fr": fr,
        "r": r,
        "c_re": 0.5 / qc,
        "c_im": asymmetry * 0.5 / qc,
        "H0_re": h0.real,
        "H0_im": h0.imag,
    }
    if name == "KidsSweepWithAffineGain":
        h1 = h0 * rng.uniform(-1e-7, 1e-7, n)
        columns |= {"H1_re": h1.real, "H1_im": h1.imag}
    else:
        columns |= {"a": rng.uniform(-1e-7, 1e-7, n), "tau": np.full(n, -36.2e-9)}
    if version == 2:
        # The drive coefficient b = 2 * a_nl * r**3, with a_nl below 0.75.
        columns["b"] = 2 * rng.uniform(0.1, 0.5, n) * r**3
    table = Table(columns)
    for c in ("f_in", "f_g", "fr"):
        table[c].unit = u.Hz
    for c, unit in _PARAMETER_UNITS.items():
        if c in table.colnames:
            table[c].unit = unit
    names = [c for c in table.colnames if c not in {"chan", "f_in"}]
    table.meta["model_schema"] = {
        "name": name,
        "version": version,
        "parameters": [{"name": c, "unit": _PARAMETER_UNITS.get(c, "")} for c in names],
    }
    return table


@pytest.mark.parametrize(("name", "version"), PHYSICAL_SCHEMAS)
def test_signals_invert_to_the_detector_state(name: str, version: int) -> None:
    # The reduction's solver, given the same model table, recovers the
    # simulated detuning and loss.
    timestream = pytest.importorskip("tolteca_kidsproc.timestream")
    n = 20
    table = _model_table(name, version, n)
    rng = np.random.default_rng(7)
    power_ref = rng.uniform(5.0, 10.0, n) << u.pW
    power = power_ref[:, np.newaxis] + (rng.normal(0.0, 0.5, (n, 300)) << u.pW)
    responsivity = rng.uniform(5e-5, 1.1e-4, n) << 1 / u.pW
    signals = get_kids_signals(power, power_ref, responsivity, table)
    solver = timestream.TimestreamSolver(table, table["chan"])
    r, x, flags = solver(signals.iq.real.T, signals.iq.imag.T)
    assert not flags.any()
    np.testing.assert_allclose(x.T, signals.x, rtol=0, atol=1e-13)
    np.testing.assert_allclose(r.T, signals.r, rtol=1e-9)


def test_detuning_follows_the_power_from_the_model_state() -> None:
    pytest.importorskip("tolteca_kidsproc.timestream")
    n = 4
    table = _model_table("KidsSweepWithAffineGain", 1, n)
    power_ref = np.full(n, 8.0) << u.pW
    delta = np.array([0.0, 0.1, -0.2]) << u.pW
    power = power_ref[:, np.newaxis] + delta
    responsivity = np.full(n, 6e-5) << 1 / u.pW
    signals = get_kids_signals(power, power_ref, responsivity, table)
    x_ref = np.asarray(table["f_in"]) / np.asarray(table["fr"]) - 1
    np.testing.assert_array_equal(signals.x[:, 0], x_ref)
    np.testing.assert_allclose(
        signals.x - x_ref[:, np.newaxis],
        np.broadcast_to((responsivity[0] * delta).value, (n, 3)),
        rtol=0,
        atol=1e-18,
    )


def test_legacy_model_tables_are_not_simulated() -> None:
    pytest.importorskip("tolteca_kidsproc.timestream")
    legacy = (
        "fp",
        "Qr",
        "Qc",
        "fr",
        "A",
        "normI",
        "normQ",
        "slopeI",
        "slopeQ",
        "interceptI",
        "interceptQ",
    )
    table = Table({"chan": [0], "f_in": [6e8], **{c: [1.0] for c in legacy}})
    for c in ("f_in", "fp", "fr"):
        table[c].unit = u.Hz
    table.meta["model_schema"] = {
        "name": "S21WithGainLinTrend",
        "version": 1,
        "parameters": [
            {"name": c, "unit": "Hz" if c in {"fp", "fr"} else ""} for c in legacy
        ],
    }
    with pytest.raises(ValueError, match="Cannot simulate"):
        get_kids_signals(
            np.ones((1, 2)) << u.pW,
            np.ones(1) << u.pW,
            np.ones(1) << 1 / u.pW,
            table,
        )
