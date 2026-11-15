import base64
import io
import json
from pathlib import Path

import astropy.units as u
import pytest
from astropy.io import fits
from dash import no_update
from dash.exceptions import PreventUpdate
from pydantic import ValidationError
from tollan.config import RuntimeContext
from tollan.utils.yaml import yaml_load
from typer.testing import CliRunner, Result

from tolteca_simu import __version__
from tolteca_simu.cli import app
from tolteca_simu.core import Simu
from tolteca_simu.planning import ObservationDescription
from tolteca_simu.toltec.exports import make_coverage_hdulist, read_results_metadata
from tolteca_simu.toltec.planning import plan_observation
from tolteca_simu.web.toltec_obs_planner import create_app
from tolteca_simu.web.toltec_obs_planner.app import ObsPlanner

FIREFLY_URL = "http://127.0.0.1:8090/firefly/"


def test_version() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == f"tolteca_simu {__version__}"


def test_show_config_applies_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "simu.yaml"
    config_path.write_text(
        "simu:\n  obs_planner:\n    subtitle: 'revision: 20250303.0'\n"
        f"    cal_data_path: {tmp_path}\n"
    )
    result = CliRunner().invoke(
        app,
        [
            "obs_planner",
            "show_config",
            "--config_paths",
            str(config_path),
            "--simu.obs_planner.target_alt_min",
            "25 deg",
        ],
    )
    assert result.exit_code == 0, result.output
    shown = json.loads(result.stdout)
    assert shown["subtitle"] == "revision: 20250303.0"
    assert shown["target_alt_min"] == "25.0 deg"


def test_planner_requires_cal_data_path() -> None:
    with pytest.raises(ValidationError, match="obs_planner"):
        Simu(RuntimeContext())
    with pytest.raises(ValidationError, match="cal_data_path"):
        Simu(RuntimeContext({"simu": {"obs_planner": {}}}))


@pytest.mark.parametrize(
    ("viewer", "match"),
    [
        ({"kind": "firefly"}, "url"),
        ({"kind": "firefly", "url": "http://127.0.0.1:8090/firefly"}, "url"),
        ({"kind": "firefly", "url": "firefly/"}, "url"),
        ({"kind": "js9"}, "union_tag_invalid"),
    ],
)
def test_viewer_is_checked(tmp_path: Path, viewer: dict, match: str) -> None:
    runtime = RuntimeContext(
        {"simu": {"obs_planner": {"cal_data_path": tmp_path, "viewer": viewer}}}
    )
    with pytest.raises(ValidationError, match=match):
        Simu(runtime)


def test_planner_defaults(tmp_path: Path) -> None:
    runtime = RuntimeContext({"simu": {"obs_planner": {"cal_data_path": tmp_path}}})
    config = Simu(runtime).config.obs_planner
    assert config.viewer.kind == "aladin_lite"
    assert config.title == "TolTEC Observation Planner"
    assert config.target_alt_min == 20 * u.deg
    assert config.server.port == 8054
    assert config.t_exp_max == 1 * u.h
    assert config.presets_path.name == "toltec_obs_planner_presets.yaml"
    # The production planner settings.
    assert config.lmt.tel_surface_rms == 100 * u.um
    assert config.toltec.det_noise_factors["am_q50"]["a1400"] == 2.19


@pytest.mark.parametrize(
    ("viewer", "scripts", "n_callbacks"),
    [
        (None, [], 30),
        (
            {"kind": "firefly", "url": FIREFLY_URL},
            [f"{FIREFLY_URL}firefly_loader.js"],
            30,
        ),
    ],
)
def test_create_app_uses_title_and_viewer(
    cal_data_path: Path, viewer: dict | None, scripts: list, n_callbacks: int
) -> None:
    settings = {"title": "Planner Test", "cal_data_path": cal_data_path}
    if viewer is not None:
        settings["viewer"] = viewer
    dash_app = create_app(RuntimeContext({"simu": {"obs_planner": settings}}))
    assert dash_app.title == "Planner Test"
    assert dash_app.config.external_scripts == scripts
    assert len(dash_app.callback_map) == n_callbacks
    # Results are computed on Execute only: the Plan or the Verify button.
    plan = [
        callback
        for callback in dash_app.callback_map.values()
        if len(callback["inputs"]) == 2
        and all(i["property"] == "n_clicks" for i in callback["inputs"])
    ]
    assert len(plan) == 1
    # As v1: the parts of the description, the loaded file and the coverage
    # unit, all as states.
    assert len(plan[0]["state"]) == 6
    # While results are computed, the two Execute buttons show it, and the
    # sky view, trajectory plots, coverage view and sensitivity tables they
    # will replace are covered. Dash keeps the running outputs only in its
    # callback list.
    callbacks = dash_app._callback_list  # noqa: SLF001
    (running,) = (c["running"] for c in callbacks if c.get("running"))
    props = sorted(key.rsplit(".", 1)[1] for key in running["running"])
    assert props == ["loading"] * 2 + ["visible"] * 4
    assert set(running["running"].values()) == {True}
    assert set(running["runningOff"].values()) == {False}


@pytest.fixture
def planner_page(cal_data_path: Path) -> ObsPlanner:
    runtime = RuntimeContext(
        {"simu": {"obs_planner": {"cal_data_path": cal_data_path}}}
    )
    simu = Simu(runtime)
    return ObsPlanner(simu.config.obs_planner, simu.make_toltec_planner())


def test_presets_follow_the_instrument_settings(planner_page: ObsPlanner) -> None:
    # The callback body is the panel's private method.
    mapping = planner_page.mapping
    apply_conditions = mapping._apply_conditions  # noqa: SLF001
    initial = mapping.preset_select.props["data"]
    ref_frames = [
        {"label": "AZ/Alt", "value": "altaz", "disabled": False},
        {"label": "RA/Dec", "value": "icrs", "disabled": False},
    ]
    # Before the page publishes the instrument settings, nothing changes.
    with pytest.raises(PreventUpdate):
        apply_conditions(None, initial, ref_frames)
    total = {"name": "toltec", "polarized": False, "array_name": "a1100"}
    polarized = total | {"polarized": True}
    # As v1: options that do not change are left alone, so a band change
    # keeps the chosen preset and frame.
    assert apply_conditions(total, initial, ref_frames) == (no_update,) * 4
    # Polarimetry enables its own preset, clears the choice, and maps in
    # RA/Dec only.
    data, key, frames, frame = apply_conditions(polarized, initial, ref_frames)
    assert key is None
    assert [d["value"] for d in data if not d["disabled"]] == [
        "toltec_polarimetry_raster"
    ]
    assert [f["value"] for f in frames if not f["disabled"]] == ["icrs"]
    assert frame == "icrs"
    # Back to total intensity, v1 clears the choice again and maps in Az/Alt.
    data, key, frames, frame = apply_conditions(total, data, frames)
    assert (data, key, frames, frame) == (initial, None, ref_frames, "altaz")


def test_preset_parameters_make_the_mapping(planner_page: ObsPlanner) -> None:
    mapping = planner_page.mapping
    make_form = mapping._make_form  # noqa: SLF001
    make_preset_data = mapping._make_preset_data  # noqa: SLF001
    key = "toltec_blank_field_raster"
    # No preset is chosen at first: no parameters, invalid as in v1.
    assert make_form("form", None) is None
    assert make_preset_data(None, [], []) == (
        None,
        "Invalid mapping settings.",
        None,
        {},
    )
    # A newly chosen preset waits for its own parameter inputs.
    with pytest.raises(PreventUpdate):
        make_preset_data(key, [1.0], [{"preset": "other", "param": "length"}])
    inputs = [getattr(item, "children", item) for item in make_form("form", key)]
    ids = [i.id for i in inputs]
    values = [i.value for i in inputs]
    data, error, message, mod = make_preset_data(key, values, ids)
    assert error is None
    assert mod == {"valid": True}
    assert message.startswith("Time to finish the pattern:")
    assert data["mapping"]["type"] == "raster"
    # A missing value makes the mapping invalid.
    data, error, _, _ = make_preset_data(key, [None, *values[1:]], ids)
    assert (data, error) == (None, "Invalid mapping settings.")


def test_verify_reports_the_loaded_file(
    planner_page: ObsPlanner, tmp_path: Path, cal_data_path: Path
) -> None:
    observation = tmp_path / "observation.yaml"
    observation.write_text(OBSERVATION_YAML)
    output = tmp_path / "out"
    result = _plan(
        tmp_path, cal_data_path, "--output_path", str(output), "--", str(observation)
    )
    assert result.exit_code == 0, result.output
    text = (output / PLAN_FILES[1]).read_text()
    contents = "data:text/plain;base64," + base64.b64encode(text.encode()).decode()
    load = planner_page.verify._load  # noqa: SLF001
    loaded, report = load(contents, "results.ecsv", 1794600000)
    description = ObservationDescription.model_validate(loaded["description"])
    assert description.target_name == "M82"
    # As v1, Execute uses the coverage unit the file records.
    assert loaded["coverage_unit"] == "depth"
    # As v1: the fields of the file, without alerts for a file made with the
    # same APT.
    (details,) = report
    assert details.children.startswith("ECSV_filename: results.ecsv\n")
    assert "depth_rms_coadd_actual:\n    a1100    : " in details.children
    other_apt = text.replace(
        planner_page.verify._apt_path,  # noqa: SLF001
        "toltec/apt/other.ecsv",
    )
    contents = "data:text/plain;base64," + base64.b64encode(other_apt.encode()).decode()
    loaded, (alert, _) = load(contents, "results.ecsv", None)
    assert loaded is not None
    assert alert.children.startswith("Mismatch APT version: toltec/apt/other.ecsv")
    loaded, (alert,) = load("data:text/plain;base64,AAAA", "x.ecsv", None)
    assert loaded is None
    assert alert.children == "Unable to parse the uploaded file."


# The description of the v1-compared case of test_toltec.py, as a user writes
# it. YAML reads an unquoted ISO time as a datetime, so t0 is quoted.
OBSERVATION_YAML = """\
target_name: M82
target: 09h55m52.4s +69d40m47s
t0: '2026-01-15T06:00:00'
mapping:
  type: lissajous
  x_length: 4 arcmin
  y_length: 4 arcmin
  x_omega: 0.5187711877562599 rad / s
  y_omega: 0.3990547598125076 rad / s
  delta: 45 deg
  rot: 0 deg
ref_frame: altaz
t_exp: 10 min
atm_model_name: am_q25
instrument:
  polarized: false
  array_name: a1100
desired_sens: 1 mJy
"""
PLAN_FILES = [
    "target_M82.lmtot",
    "toltec_obs_planner_results.ecsv",
    "obsplanner_toltec_a1100_cov.fits",
]


def _plan(tmp_path: Path, cal_data_path: Path, *args: str) -> Result:
    config_path = tmp_path / "simu.yaml"
    config_path.write_text(
        f"simu:\n  obs_planner:\n    cal_data_path: {cal_data_path}\n"
    )
    return CliRunner().invoke(
        app, ["obs_planner", "plan", "--config_paths", str(config_path), *args]
    )


def test_plan_writes_the_planner_files(tmp_path: Path, cal_data_path: Path) -> None:
    observation = tmp_path / "observation.yaml"
    observation.write_text(OBSERVATION_YAML)
    output = tmp_path / "out"
    result = _plan(
        tmp_path, cal_data_path, "--output_path", str(output), "--", str(observation)
    )
    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in output.iterdir()) == sorted(PLAN_FILES)
    description = ObservationDescription.model_validate(yaml_load(observation))
    runtime = RuntimeContext(
        {"simu": {"obs_planner": {"cal_data_path": cal_data_path}}}
    )
    plan = plan_observation(description, Simu(runtime).make_toltec_planner())
    reloaded, _ = read_results_metadata((output / PLAN_FILES[1]).read_text())
    assert reloaded == description
    buffer = io.BytesIO()
    make_coverage_hdulist(plan.result, "depth").writeto(buffer)
    assert (output / PLAN_FILES[2]).read_bytes() == buffer.getvalue()


def test_plan_replans_a_results_file(tmp_path: Path, cal_data_path: Path) -> None:
    observation = tmp_path / "observation.yaml"
    observation.write_text(OBSERVATION_YAML)
    first, second, third = (tmp_path / name for name in ("first", "second", "third"))
    _plan(
        tmp_path,
        cal_data_path,
        "--output_path",
        str(first),
        "--coverage_unit",
        "time",
        "--",
        str(observation),
    )
    results = first / PLAN_FILES[1]
    # As the Verify tab: the file's description in the file's coverage unit.
    result = _plan(
        tmp_path, cal_data_path, "--output_path", str(second), "--", str(results)
    )
    assert result.exit_code == 0, result.output
    description, _ = read_results_metadata(results.read_text())
    replanned, meta = read_results_metadata((second / PLAN_FILES[1]).read_text())
    assert replanned == description
    assert meta["coverage_unit"] == "time"
    hdulist = fits.open(io.BytesIO((second / PLAN_FILES[2]).read_bytes()))
    assert hdulist["cov_raw"].header["BUNIT"] == "s / pix"
    # An explicit unit takes precedence.
    result = _plan(
        tmp_path,
        cal_data_path,
        "--output_path",
        str(third),
        "--coverage_unit",
        "depth",
        "--",
        str(results),
    )
    assert result.exit_code == 0, result.output
    hdulist = fits.open(io.BytesIO((third / PLAN_FILES[2]).read_bytes()))
    assert hdulist["cov_raw"].header["BUNIT"] == "mJy / beam"


def test_plan_keeps_existing_files(tmp_path: Path, cal_data_path: Path) -> None:
    observation = tmp_path / "observation.yaml"
    observation.write_text(OBSERVATION_YAML)
    output = tmp_path / "out"
    args = ["--output_path", str(output), "--", str(observation)]
    _plan(tmp_path, cal_data_path, *args)
    script = (output / PLAN_FILES[0]).read_text()
    result = _plan(tmp_path, cal_data_path, *args)
    assert result.exit_code != 0
    assert "--overwrite" in result.output
    assert (output / PLAN_FILES[0]).read_text() == script
    result = _plan(tmp_path, cal_data_path, "--overwrite", *args)
    assert result.exit_code == 0, result.output
