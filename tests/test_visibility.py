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
from tolteca_simu.web.toltec_obs_planner.target import (
    TargetPanel,
    check_date,
    check_start_time,
)
from tolteca_simu.web.toltec_obs_planner.visibility import make_visibility_figure

# Recorded with v1 on unity-toltec4; see the file's provenance fields.
REFERENCE = json.loads(
    (Path(__file__).parent / "data" / "v1_visibility_reference.json").read_text()
)
# v1 ObsPlannerTargetSelect.validate_date and validate_time.
CHECK_REFERENCE = json.loads(
    (Path(__file__).parent / "data" / "v1_target_check_reference.json").read_text()
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


@pytest.mark.parametrize(
    "case",
    CHECK_REFERENCE["cases"],
    ids=lambda c: f"{c['coord']}-{c['date']}-{c['time']}",
)
def test_target_checks_match_v1(case: dict) -> None:
    target = SkyCoord(case["coord"])
    observer = get_lmt_observer()
    message, valid = check_date(target, Time(case["date"]), observer, 20 * u.deg)
    assert (message, valid) == (case["date_feedback"], case["date_type"] == "valid")
    message, valid = check_start_time(
        target, Time(f"{case['date']} {case['time']}"), observer, 20 * u.deg
    )
    assert valid == (case["time_type"] == "valid")
    # The v3 text fixes two typos of v1.
    expected = (
        case["time_feedback"]
        .replace("Alt =-", "Alt = -")
        .replace("Alt =1", "Alt = 1")
        .replace("to observer", "to observe")
    )
    assert message == expected


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


def test_date_and_time_inputs_use_the_v1_formats() -> None:
    panel = TargetPanel(target_alt_min=20 * u.deg)
    resolved = {"name": "M1", "ra_deg": 83.6324, "dec_deg": 22.0174}
    # The panel's callback bodies are private methods.
    check_date = panel._check_date  # noqa: SLF001
    check_time = panel._check_time  # noqa: SLF001
    for date in ("2026/10/19", "19-10-2026", "2026-13-45", ""):
        error, _, mod = check_date(date, resolved)
        assert (error, mod) == ("Invalid Date. Use yyyy-mm-dd.", {})
    _, message, mod = check_date("2026-10-19", resolved)
    assert message.startswith("Total up-time:")
    assert mod == {"valid": True}
    for time in ("6:00", "06:00", "06:00:00.5", "25:00:00"):
        error, _, _ = check_time(time, "2026-10-19", resolved)
        assert error == "Invalid time. Use HH:MM:SS."
    _, message, _ = check_time("06:00:00", "2026-10-19", resolved)
    assert message.startswith("Target Az = ")
