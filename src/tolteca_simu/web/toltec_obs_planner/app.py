"""Planner page layout and application factory."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import dash_mantine_components as dmc
from dash import Dash, Input, Output, dcc
from dash_component_template import Template

from tolteca_simu.core import Simu
from tolteca_simu.planning import MappingPresets, ObservationDescription

from .mapping import MappingPanel
from .target import TargetPanel
from .trajectory import TrajectoryPanel
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

    The page keeps the observation description, serialized as JSON, in its
    `description` store; every result is computed from it.

    Parameters
    ----------
    config : tolteca_simu.config.ObsPlannerConfig
        Title, subtitle, presets, and limits.
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
        main = shell.child[dmc.AppShellMain]()
        self.description = main.child[dcc.Store](data=None)
        grid = main.child[dmc.Grid](gutter="md")
        controls = grid.child[dmc.GridCol](span={"base": 12, "md": 4, "xl": 3})
        results = grid.child[dmc.GridCol](span={"base": 12, "md": 8, "xl": 9})
        controls = controls.child[dmc.Stack](gap="md")
        results = results.child[dmc.Stack](gap="md")
        self.target = controls.child(TargetPanel())
        self.mapping = controls.child(
            MappingPanel(
                MappingPresets.from_yaml(config.presets_path),
                t_exp_max=config.t_exp_max,
            )
        )
        self.visibility = results.child(
            VisibilityPanel(
                description=self.description, target_alt_min=config.target_alt_min
            )
        )
        self.trajectory = results.child(TrajectoryPanel(description=self.description))

    def setup_callbacks(self, app: Dash) -> None:
        """Combine the panels' parts into the observation description.

        Parameters
        ----------
        app : dash.Dash
            Application receiving the callbacks.
        """

        @app.callback(
            Output(self.description(), "data"),
            Input(self.target.target(), "data"),
            Input(self.mapping.mapping(), "data"),
        )
        def _make_description(
            target: dict | None, mapping: dict | None
        ) -> dict[str, Any] | None:
            if target is None or mapping is None:
                return None
            description = ObservationDescription.model_validate(target | mapping)
            return description.model_dump(mode="json")
