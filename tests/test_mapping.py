"""Mapping patterns and trajectories against the production planner.

Reference: v1 obs_planner @ 639b8a1 on the production presets rev20251014.0,
recorded on unity-toltec4 (see the file's provenance fields).
"""

import json
from pathlib import Path

import astropy.units as u
import numpy as np
import pytest
from astropy.time import Time

from tolteca_simu.lmt import get_lmt_observer
from tolteca_simu.mapping import PatternKind, RasterPattern
from tolteca_simu.planning import (
    MappingPresets,
    get_trajectory,
    parse_target,
)
from tolteca_simu.planning.presets import get_default_presets_path

REFERENCE = json.loads(
    (Path(__file__).parent / "data" / "v1_mapping_reference.json").read_text()
)
PRESETS = MappingPresets.from_yaml(get_default_presets_path())
TARGET = parse_target(REFERENCE["target_data"]["name"])
T0 = Time(f"{REFERENCE['target_data']['date']} {REFERENCE['target_data']['time']}")


@pytest.fixture(
    params=REFERENCE["cases"], ids=lambda c: f"{c['preset']}-{c['ref_frame']}"
)
def case(request: pytest.FixtureRequest) -> dict:
    return request.param


def _make_mapping(key: str) -> tuple:
    preset = PRESETS.get(key)
    return preset.make_mapping({name: p.value for name, p in preset.params.items()})


def test_preset_mapping_matches_v1(case: dict) -> None:
    pattern, t_exp = _make_mapping(case["preset"])
    assert pattern.type == case["mapping_config"]["type"]
    assert pattern.t_pattern.to_value(u.s) == pytest.approx(
        case["t_pattern_s"], rel=1e-12
    )
    # v1 records the exposure time as t_pattern when the preset has none.
    t_exp_s = pattern.t_pattern if t_exp is None else t_exp
    assert t_exp_s.to_value(u.s) == pytest.approx(case["t_exp_s"], rel=1e-12)
    # The Lissajous speed rescaling is applied to the recorded frequencies. v1
    # holds lengths in degrees, which changes the last bit of the Rastajous ones.
    for name, value in case["mapping_config"].items():
        if "omega" in name:
            assert getattr(pattern, name).to_value(u.rad / u.s) == pytest.approx(
                u.Quantity(value).to_value(u.rad / u.s), rel=1e-15
            )


def test_trajectory_matches_v1(case: dict) -> None:
    pattern, _ = _make_mapping(case["preset"])
    trajectory = get_trajectory(
        pattern,
        TARGET,
        T0,
        t_exp=case["t_exp_s"] * u.s,
        ref_frame=case["ref_frame"],
        observer=get_lmt_observer(),
    )
    assert len(trajectory.t) == case["n_samples"]
    assert int(trajectory.turnaround.sum()) == case["n_overhead"]
    i = np.array(case["sample_index"])
    assert list(trajectory.turnaround[i]) == case["overhead_at_samples"]
    np.testing.assert_allclose(
        trajectory.t[i].to_value(u.s), case["t_s"], rtol=0, atol=1e-9
    )
    for values, key in (
        (trajectory.dlon, "dlon_arcmin"),
        (trajectory.dlat, "dlat_arcmin"),
    ):
        np.testing.assert_allclose(
            values[i].to_value(u.arcmin), case[key], rtol=0, atol=1e-12
        )
    # Measured differences are below 1e-8 arcsec; v1 ran astropy 5.3.
    for values, key in (
        (trajectory.coords_icrs.ra, "ra_deg"),
        (trajectory.coords_icrs.dec, "dec_deg"),
        (trajectory.coords_altaz.az, "az_deg"),
        (trajectory.coords_altaz.alt, "alt_deg"),
        (trajectory.target_altaz.alt, "target_alt_deg"),
    ):
        np.testing.assert_allclose(
            values[i].to_value(u.deg), case[key], rtol=0, atol=1e-10
        )


def test_raster_kinds_and_single_scan() -> None:
    raster = RasterPattern(
        length=10 * u.arcmin,
        space=1 * u.arcmin,
        n_scans=1,
        rot=0 * u.deg,
        speed=1 * u.arcmin / u.s,
        t_turnaround=5 * u.s,
    )
    assert raster.pattern_kind in PatternKind.raster_like
    assert raster.t_pattern == 10 * u.s
    t = np.array([0, 5, 10]) << u.s
    dlon, dlat = raster.offsets(t)
    np.testing.assert_allclose(dlon.to_value(u.arcmin), [-5, 0, 5])
    np.testing.assert_allclose(dlat.to_value(u.arcmin), [0, 0, 0])
    assert not raster.turnaround_mask(t).any()


def test_rastajous_is_raster_like() -> None:
    pattern, _ = _make_mapping("toltec_blank_field_rastajous")
    assert pattern.pattern_kind in PatternKind.raster_like
