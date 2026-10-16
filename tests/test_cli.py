import json
from pathlib import Path

import astropy.units as u
from tollan.config import RuntimeContext
from typer.testing import CliRunner

from tolteca_simu import __version__
from tolteca_simu.cli import app
from tolteca_simu.core import Simu
from tolteca_simu.web.toltec_obs_planner import create_app


def test_version() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == f"tolteca_simu {__version__}"


def test_show_config_applies_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "simu.yaml"
    config_path.write_text(
        "simu:\n  obs_planner:\n    subtitle: 'revision: 20250303.0'\n"
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


def test_defaults_without_simu_section() -> None:
    config = Simu(RuntimeContext()).config.obs_planner
    assert config.title == "TolTEC Observation Planner"
    assert config.target_alt_min == 20 * u.deg
    assert config.server.port == 8054


def test_create_app_uses_title() -> None:
    runtime = RuntimeContext({"simu": {"obs_planner": {"title": "Planner Test"}}})
    dash_app = create_app(runtime)
    assert dash_app.title == "Planner Test"
    assert len(dash_app.callback_map) == 4
