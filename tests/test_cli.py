import json
from pathlib import Path

import astropy.units as u
import pytest
from pydantic import ValidationError
from tollan.config import RuntimeContext
from typer.testing import CliRunner

from tolteca_simu import __version__
from tolteca_simu.cli import app
from tolteca_simu.core import Simu
from tolteca_simu.web.toltec_obs_planner import create_app

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
        (None, [], 16),
        (
            {"kind": "firefly", "url": FIREFLY_URL},
            [f"{FIREFLY_URL}firefly_loader.js"],
            16,
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
