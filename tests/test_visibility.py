"""Target visibility against the production planner (v1 obs_planner @ 639b8a1)."""

import json
from pathlib import Path

import astropy.units as u
import numpy as np
import pytest
from astropy.coordinates import SkyCoord
from astropy.time import Time

from tolteca_simu.lmt import get_lmt_observer
from tolteca_simu.planning import get_target_visibility
from tolteca_simu.web.toltec_obs_planner.visibility import make_visibility_figure

# Recorded with v1 on unity-toltec4; see the file's provenance fields.
REFERENCE = json.loads(
    (Path(__file__).parent / "data" / "v1_visibility_reference.json").read_text()
)


@pytest.fixture(params=REFERENCE["cases"], ids=lambda c: c["coord"])
def case(request: pytest.FixtureRequest) -> dict:
    return request.param


def test_altitude_matches_v1(case: dict) -> None:
    visibility = get_target_visibility(
        SkyCoord(case["coord"]), Time(case["t0"]), get_lmt_observer()
    )
    assert visibility.time[0].iso == case["day_start"]
    assert len(visibility.time) == 24 * 60 + 1
    alt = visibility.alt.to_value(u.deg)
    np.testing.assert_allclose(
        alt[::60], case["alt_deg_every_60min"], rtol=0, atol=1e-10
    )
    assert int(alt.argmax()) == case["i_alt_max"]
    assert alt.max() == pytest.approx(case["alt_deg_max"], abs=1e-10)


def test_sun_times_match_v1(case: dict) -> None:
    visibility = get_target_visibility(
        SkyCoord(case["coord"]), Time(case["t0"]), get_lmt_observer()
    )
    # astroplan interpolates the horizon crossing on a grid; 1 ms bounds the
    # float differences between the v1 and v3 environments.
    for key in ("sun_rise_time", "sun_set_time"):
        dt = getattr(visibility, key) - Time(case[key])
        assert abs(dt.to_value(u.s)) < 1e-3


def test_start_time_position() -> None:
    # 2026-01-15 06:00 UT is night at the LMT.
    visibility = get_target_visibility(
        SkyCoord("09h55m52.4s +69d40m47s"),
        Time("2026-01-15 06:00:00"),
        get_lmt_observer(),
    )
    assert visibility.is_night_t0
    i_t0 = 6 * 60
    assert visibility.altaz_t0.alt.to_value(u.deg) == pytest.approx(
        visibility.alt[i_t0].to_value(u.deg), abs=1e-9
    )


def test_figure_marks_interval_and_night() -> None:
    case = REFERENCE["cases"][0]
    t0 = Time(case["t0"])
    visibility = get_target_visibility(SkyCoord(case["coord"]), t0, get_lmt_observer())
    fig = make_visibility_figure(visibility, t0 + 2 * u.min, 20 * u.deg)
    lines = [trace for trace in fig.data if trace.mode == "lines"]
    assert sum(len(trace.x) for trace in lines) == 24 * 60 + 1
    assert {trace.name for trace in lines} == {"Daytime", "Night"}
    (marker,) = (trace for trace in fig.data if trace.mode == "markers")
    # v1 marks from the sample before t0 through the sample after t1.
    assert len(marker.x) == 4
