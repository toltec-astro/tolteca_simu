"""Time cost and exports against the production planner.

Reference: v1 obs_planner @ 639b8a1 results table (``proj_*`` columns) and LMT
OT scripts, recorded on unity-toltec4 (see the file's provenance fields).
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import astropy.units as u
import pytest
from astropy.time import Time

from tolteca_simu.cal_data import CalDataStore
from tolteca_simu.lmt import get_lmt_observer
from tolteca_simu.lmtot import make_lmtot_script
from tolteca_simu.planning import (
    MappingPresets,
    ObservationDescription,
    get_trajectory,
    parse_target,
)
from tolteca_simu.planning.presets import get_default_presets_path
from tolteca_simu.toltec.exports import (
    make_coverage_hdulist,
    make_results_table,
    read_results_metadata,
    write_results_ecsv,
)
from tolteca_simu.toltec.planning import ToltecPlanner
from tolteca_simu.toltec.settings import ToltecSettings
from tolteca_simu.toltec.time_cost import get_time_cost

REFERENCE = json.loads(
    (Path(__file__).parent / "data" / "v1_toltec_reference.json").read_text()
)
PRESETS = MappingPresets.from_yaml(get_default_presets_path())
APT = "toltec/apt/apt_GW_v8_with_fg_pg_loc_ori_flipped_flag_fixed.ecsv"
RTOL = 1e-12
NUMBER = re.compile(r"-?\d+\.\d+(?:e-?\d+)?")
V1_COLUMNS = [
    "array_name",
    "alt_mean",
    "P",
    "n_dets_info",
    "net_cmb",
    "nefd",
    "nep",
    "nefd_I",
    "nefd_QU",
    "dsens_I",
    "dsens_QU",
    "mapping_speed_I",
    "mapping_speed_QU",
    "polarized",
    "depth_stokes_params",
    "depth_rms",
    "t_exp",
    "t_exp_eff",
    "map_area",
    "n_passes",
    "depth_rms_coadd_desired",
    "depth_rms_coadd_actual",
    "proj_science_time",
    "proj_science_time_per_night",
    "proj_n_nights",
    "proj_science_overhead_time",
    "proj_total_time",
    "proj_overhead_time",
    "proj_overhead_percent",
]


def _description(c: dict) -> ObservationDescription:
    target_data = REFERENCE["target_data"]
    preset = PRESETS.get(c["preset"])
    pattern, t_exp = preset.make_mapping({n: p.value for n, p in preset.params.items()})
    return ObservationDescription(
        target_name=target_data["name"],
        target=parse_target(target_data["name"]),
        t0=Time(f"{target_data['date']} {target_data['time']}"),
        mapping=pattern,
        ref_frame=c["ref_frame"],
        t_exp=t_exp,
        atm_model_name=c["atm_model_name"],
        instrument=ToltecSettings(
            polarized=c["stokes_params"] == "QU", array_name=c["array_name"]
        ),
        desired_sens=1 * u.mJy,
    )


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
    description = _description(c)
    observer = get_lmt_observer()
    trajectory = get_trajectory(
        description.mapping,
        description.target,
        description.t0,
        t_exp=description.get_t_exp(),
        ref_frame=description.ref_frame,
        observer=observer,
    )
    result = planner.plan(description, trajectory, observer)
    time_cost = get_time_cost(result.n_passes, result.t_exp, result.t_exp_eff)
    return c, description, result, time_cost


def test_time_cost_matches_v1(case: tuple) -> None:
    c, _, _, time_cost = case
    row = c["sens_table"][0]
    assert time_cost.science_time.to_value(u.h) == pytest.approx(
        row["proj_science_time"], rel=RTOL
    )
    assert time_cost.n_nights == row["proj_n_nights"]
    assert time_cost.science_overhead.to_value(u.h) == pytest.approx(
        row["proj_science_overhead_time"], rel=RTOL, abs=1e-15
    )
    assert time_cost.total_time.to_value(u.h) == pytest.approx(
        row["proj_total_time"], rel=RTOL
    )
    assert time_cost.overhead_time.to_value(u.h) == pytest.approx(
        row["proj_overhead_time"], rel=RTOL
    )
    assert f"{time_cost.overhead_fraction:.1%}" == row["proj_overhead_percent"]


def test_lmtot_script_matches_v1(case: tuple) -> None:
    c, description, _, _ = case
    date = c["lmtot"].split('-Date "')[1].split('"')[0]
    created_at = datetime.strptime(date, "%a %b %d %H:%M:%S UTC %Y").replace(tzinfo=UTC)
    script = make_lmtot_script(
        description, author="obs_planner_simu", created_at=created_at
    )
    lines, reference = script.splitlines(), c["lmtot"].splitlines()
    assert len(lines) == len(reference)
    for line, ref in zip(lines, reference, strict=True):
        assert NUMBER.sub("#", line) == NUMBER.sub("#", ref)
        # v1 holds lengths in degrees; Rastajous frequencies differ in the last bit.
        for value, ref_value in zip(
            NUMBER.findall(line), NUMBER.findall(ref), strict=True
        ):
            assert float(value) == pytest.approx(float(ref_value), rel=1e-15)


def test_results_table_matches_v1(case: tuple) -> None:
    c, description, result, time_cost = case
    table = make_results_table(
        description, result, time_cost, APT, created_at=datetime.now(UTC)
    )
    assert table.colnames == V1_COLUMNS
    for row in c["sens_table"]:
        mine = table[table["array_name"] == row["array_name"]][0]
        for key, value in row.items():
            mine_value = getattr(mine[key], "value", mine[key])
            if key == "proj_science_time_per_night":
                # v1 records the number of nights in this column.
                assert mine[key] == 4 * u.h
            elif key == "map_area":
                # FFT round-off at the 10 % mask threshold; see test_toltec.
                assert mine_value == pytest.approx(value, rel=1e-3)
            elif isinstance(value, float):
                assert mine_value == pytest.approx(value, rel=RTOL, abs=1e-15)
            else:
                assert mine_value == value


def test_results_ecsv_reloads_description(case: tuple) -> None:
    _, description, result, time_cost = case
    table = make_results_table(
        description, result, time_cost, APT, created_at=datetime.now(UTC)
    )
    reloaded, meta = read_results_metadata(write_results_ecsv(table))
    assert reloaded == description
    assert meta["apt"] == APT


def test_coverage_fits_headers_match_v1(case: tuple) -> None:
    c, _, result, _ = case
    hdulist = make_coverage_hdulist(result, c["coverage_map_type"])
    assert [hdu.header["EXTNAME"] for hdu in hdulist[1:]] == [
        ref["extname"] for ref in c["hdus"]
    ]
    for key, value in c["primary_header"].items():
        assert hdulist[0].header[key] == value
    for hdu, ref in zip(hdulist[1:], c["hdus"], strict=True):
        assert hdu.header["BUNIT"] == ref["bunit"]
        assert hdu.data.sum() == pytest.approx(ref["sum"], rel=RTOL)


def test_reading_a_table_without_description_fails() -> None:
    with pytest.raises(ValueError, match="no observation description"):
        read_results_metadata(
            "# %ECSV 1.0\n# ---\n# datatype:\n# - {name: a, datatype: int64}\na\n1\n"
        )
