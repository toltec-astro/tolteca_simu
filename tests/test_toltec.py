"""TolTEC footprint, coverage, and sensitivity against the production planner.

Reference: v1 obs_planner @ 639b8a1 (Toltec.make_traj_data) with the production
settings, recorded on unity-toltec4 (see the file's provenance fields).
"""

import json
from pathlib import Path

import astropy.units as u
import numpy as np
import pytest
from astropy.time import Time

from tolteca_simu.cal_data import CalDataStore
from tolteca_simu.lmt import get_lmt_observer
from tolteca_simu.planning import MappingPresets, get_trajectory, parse_target
from tolteca_simu.planning.presets import get_default_presets_path
from tolteca_simu.toltec.planning import (
    ToltecPlanner,
    ToltecPlanningResult,
    get_toltec_planning_result,
)

REFERENCE = json.loads(
    (Path(__file__).parent / "data" / "v1_toltec_reference.json").read_text()
)
PRESETS = MappingPresets.from_yaml(get_default_presets_path())
TARGET = parse_target(REFERENCE["target_data"]["name"])
T0 = Time(f"{REFERENCE['target_data']['date']} {REFERENCE['target_data']['time']}")
APT = "toltec/apt/apt_GW_v8_with_fg_pg_loc_ori_flipped_flag_fixed.ecsv"
RTOL = 1e-12


@pytest.fixture(scope="module")
def planner(cal_data_path: Path) -> ToltecPlanner:
    return ToltecPlanner(
        CalDataStore(cal_data_path),
        apt_path=APT,
        tel_surface_rms=100 * u.um,
        det_noise_factors=REFERENCE["settings"]["det_noise_factors"],
    )


@pytest.fixture(
    scope="module",
    params=REFERENCE["cases"],
    ids=lambda c: f"{c['preset']}-{c['array_name']}-{c['atm_model_name']}",
)
def case(request: pytest.FixtureRequest, planner: ToltecPlanner) -> tuple:
    c = request.param
    preset = PRESETS.get(c["preset"])
    pattern, t_exp = preset.make_mapping({n: p.value for n, p in preset.params.items()})
    t_exp = pattern.t_pattern if t_exp is None else t_exp
    observer = get_lmt_observer()
    trajectory = get_trajectory(
        pattern, TARGET, T0, t_exp=t_exp, ref_frame=c["ref_frame"], observer=observer
    )
    result = get_toltec_planning_result(
        pattern=pattern,
        trajectory=trajectory,
        target=TARGET,
        observer=observer,
        t_exp=t_exp,
        apt=planner.apt,
        n_dets_designed=planner.n_dets_designed,
        loading_models=planner.get_loading_models(c["atm_model_name"]),
        array_name=c["array_name"],
        polarized=c["stokes_params"] == "QU",
        desired_sens=1 * u.mJy,
    )
    return c, t_exp, result


def _block_sum(image: np.ndarray, n: int = 8) -> np.ndarray:
    ny, nx = image.shape
    ys = np.linspace(0, ny, n + 1).astype(int)
    xs = np.linspace(0, nx, n + 1).astype(int)
    return np.array(
        [
            [image[ys[i] : ys[i + 1], xs[j] : xs[j + 1]].sum() for j in range(n)]
            for i in range(n)
        ]
    )


def test_footprint_matches_v1(case: tuple) -> None:
    c, _, result = case
    footprint = result.footprint
    assert len(footprint.dlon) == c["n_dets"]
    i = np.array(c["det_sample_index"])
    np.testing.assert_allclose(
        footprint.dlon[i].to_value(u.arcmin), c["det_dlon_arcmin"], rtol=0, atol=1e-12
    )
    np.testing.assert_allclose(
        footprint.dlat[i].to_value(u.arcmin), c["det_dlat_arcmin"], rtol=0, atol=1e-12
    )
    np.testing.assert_allclose(
        footprint.coords_icrs.ra.degree[i], c["det_ra_deg"], rtol=0, atol=1e-10
    )
    np.testing.assert_allclose(
        footprint.coords_icrs.dec.degree[i], c["det_dec_deg"], rtol=0, atol=1e-10
    )


def test_coverage_matches_v1(case: tuple) -> None:
    c, _, result = case
    header = result.coverage.wcs.to_header()
    reference = c["hdus"]
    assert list(result.coverage.data.shape) == reference[0]["shape"]
    np.testing.assert_allclose(
        [header["CRVAL1"], header["CRVAL2"]], reference[0]["crval"], rtol=RTOL
    )
    np.testing.assert_allclose(
        [header["CRPIX1"], header["CRPIX2"]], reference[0]["crpix"], rtol=RTOL
    )
    np.testing.assert_allclose(
        [header["CDELT1"], header["CDELT2"]], reference[0]["cdelt"], rtol=RTOL
    )
    # v1 stores the turnaround-free map first, in the requested unit.
    if c["coverage_map_type"] == "time":
        maps = [result.coverage.data_on_scan, result.coverage.data]
    else:
        maps = [result.depth.depth, result.depth.depth_all]
    for image, ref in zip(maps, reference, strict=True):
        assert image.sum() == pytest.approx(ref["sum"], rel=RTOL)
        assert image.max() == pytest.approx(ref["max"], rel=RTOL)
        np.testing.assert_allclose(
            _block_sum(image), ref["block_sum_8x8"], rtol=0, atol=RTOL * ref["sum"]
        )


def _summary_value(result: ToltecPlanningResult, row: dict, key: str) -> float:
    s = result.summaries[row["array_name"]]
    values = {
        "alt_mean": s.alt_mean.to_value(u.deg),
        "P": s.power.to_value(u.pW),
        "net_cmb": s.noise.net_cmb.to_value(u.mK * u.Hz**-0.5),
        "nefd": s.noise.nefd.to_value(u.mJy * u.Hz**-0.5),
        "nep": s.noise.nep.to_value(u.aW * u.Hz**-0.5),
        "depth_rms": s.depth_rms.to_value(u.mJy),
        "depth_rms_coadd_actual": s.depth_rms_coadd.to_value(u.mJy),
    }
    stokes = "QU" if result.polarized else "I"
    values[f"nefd_{stokes}"] = s.nefd.to_value(u.mJy * u.Hz**-0.5)
    values[f"dsens_{stokes}"] = s.detector_sensitivity.to_value(u.mJy * u.s**0.5)
    return values[key]


@pytest.mark.parametrize(
    "key",
    ["alt_mean", "P", "net_cmb", "nefd", "nep", "nefd_S", "dsens_S", "depth_rms"],
)
def test_sensitivity_matches_v1(case: tuple, key: str) -> None:
    c, _, result = case
    stokes = "QU" if result.polarized else "I"
    key = key.replace("_S", f"_{stokes}")
    for row in c["sens_table"]:
        assert _summary_value(result, row, key) == pytest.approx(row[key], rel=RTOL)


def test_passes_and_times_match_v1(case: tuple) -> None:
    c, t_exp, result = case
    stokes = "QU" if result.polarized else "I"
    for row in c["sens_table"]:
        s = result.summaries[row["array_name"]]
        assert result.n_passes == row["n_passes"]
        assert f"{s.n_dets} / {s.n_dets_designed}" in row["n_dets_info"]
        assert (
            f"{s.mapping_speed.value:.1f}" == row[f"mapping_speed_{stokes}"].split()[0]
        )
        assert _summary_value(result, row, "depth_rms_coadd_actual") == pytest.approx(
            row["depth_rms_coadd_actual"], rel=RTOL
        )
        # The reference keeps v1's time unit, that of the preset's exposure time.
        assert result.t_exp_eff.to_value(t_exp.unit) == pytest.approx(
            row["t_exp_eff"], rel=RTOL
        )
        # Raster coverage has pixels exactly at the 10 % mask threshold, which
        # FFT round-off flips: 18 of 95,657 pixels in the polarimetry raster.
        assert result.depth.map_area.to_value(u.deg**2) == pytest.approx(
            row["map_area"], rel=1e-3
        )


def test_q75_atmosphere_loads(planner: ToltecPlanner) -> None:
    # v1 on unity-toltec4 could not load am_q75, so this has no reference.
    models = planner.get_loading_models("am_q75")
    q25 = planner.get_loading_models("am_q25")
    alt = 45 * u.deg
    for name, model in models.items():
        assert model.get_power(alt) > q25[name].get_power(alt)
