"""Planner page layout and application factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

import dash_mantine_components as dmc
from dash import Dash
from dash_component_template import Template

from tolteca_simu.core import Simu

from .target import TargetPanel
from .visibility import VisibilityPanel

if TYPE_CHECKING:
    from tollan.config import RuntimeContext

    from tolteca_simu.config import ObsPlannerConfig

__all__ = ["ObsPlanner", "create_app"]


def create_app(runtime: RuntimeContext) -> Dash:
    """Create the planner from the ``simu.obs_planner`` settings.

    Parameters
    ----------
    runtime : tollan.config.RuntimeContext
        Runtime supplying the ``simu`` settings.

    Returns
    -------
    dash.Dash
        Application with its layout and callbacks; no server is started.
    """
    config = Simu(runtime).config.obs_planner
    planner = ObsPlanner(config)
    app = Dash(__name__, title=config.title)
    app.layout = planner.layout()
    planner.register_callbacks(app)
    return app


class ObsPlanner(Template):
    """The planner page: description controls beside the planning results.

    Parameters
    ----------
    config : tolteca_simu.config.ObsPlannerConfig
        Title, subtitle, and minimum target elevation.
    """

    def __init__(self, config: ObsPlannerConfig) -> None:
        super().__init__()
        provider = self.child[dmc.MantineProvider]()
        shell = provider.child[dmc.AppShell](header={"height": 48}, padding="md")
        header = shell.child[dmc.AppShellHeader]().child[dmc.Group](
            px="md", h="100%", gap="sm"
        )
        header.child[dmc.Title](config.title, order=4)
        header.child[dmc.Text](config.subtitle, size="sm", c="dimmed")
        grid = shell.child[dmc.AppShellMain]().child[dmc.Grid](gutter="md")
        controls = grid.child[dmc.GridCol](span={"base": 12, "md": 4})
        results = grid.child[dmc.GridCol](span={"base": 12, "md": 8})
        self.target = controls.child(TargetPanel())
        self.visibility = results.child(
            VisibilityPanel(
                description=self.target.description,
                target_alt_min=config.target_alt_min,
            )
        )
