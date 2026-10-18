from importlib.resources import files
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError
from tollan.config import RuntimeContext
from tollan.utils.yaml import yaml_load

from tolteca_simu.core import Simu
from tolteca_simu.web.toltec_obs_planner import server

PROFILE = Path(str(files("tolteca_simu"))) / "data/location/run/tolteca_simu.default"


def test_default_profile_files() -> None:
    assert (PROFILE / "justfile").is_file()
    recipes = (PROFILE / "just.d/00_default.just").read_text()
    for recipe in ("obs_planner", "obs_planner_serve", "show_config"):
        assert f"\n{recipe} *ARGS:" in recipes


def test_default_profile_config_validates(cal_data_path: Path) -> None:
    config = cast("dict[str, Any]", yaml_load(PROFILE / "config.d/00_default.yaml"))
    # The profile names the store relative to the location root.
    assert config["simu"]["obs_planner"]["cal_data_path"] == "src/tolteca_cal_data"
    config["simu"]["obs_planner"]["cal_data_path"] = str(cal_data_path)
    planner = Simu(RuntimeContext(config)).config.obs_planner
    assert planner.server.port == 8054
    assert planner.server.url_base_pathname == "/"


def test_serve_runs_gunicorn_with_server_settings(
    cal_data_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: dict[str, Any] = {}

    def _run(self: server.PlannerServer) -> None:
        started["options"] = self._options
        started["app"] = self._application

    monkeypatch.setattr(server.PlannerServer, "run", _run)
    runtime = RuntimeContext(
        {
            "simu": {
                "obs_planner": {
                    "cal_data_path": cal_data_path,
                    "server": {
                        "host": "0.0.0.0",  # noqa: S104
                        "port": 8100,
                        "workers": 2,
                        "url_base_pathname": "/toltec_obs_planner/",
                    },
                }
            }
        }
    )
    server.serve(runtime)
    assert started["options"] == {"bind": "0.0.0.0:8100", "workers": 2, "timeout": 120}
    client = started["app"].test_client()
    assert client.get("/toltec_obs_planner/").status_code == 200
    assert client.get("/").status_code == 404


@pytest.mark.parametrize("path", ["toltec_obs_planner/", "/toltec_obs_planner"])
def test_url_base_pathname_needs_slashes(tmp_path: Path, path: str) -> None:
    runtime = RuntimeContext(
        {
            "simu": {
                "obs_planner": {
                    "cal_data_path": tmp_path,
                    "server": {"url_base_pathname": path},
                }
            }
        }
    )
    with pytest.raises(ValidationError, match="url_base_pathname"):
        Simu(runtime)
