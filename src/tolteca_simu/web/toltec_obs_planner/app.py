"""Planner page layout and application factory."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import dash_mantine_components as dmc
from dash import Dash, Input, Output, dcc
from dash_component_template import Template

from tolteca_simu.cal_data import CalDataStore
from tolteca_simu.core import Simu
from tolteca_simu.lmt import get_lmt_observer
from tolteca_simu.planning import MappingPresets, ObservationDescription, get_trajectory
from tolteca_simu.toltec import TOLTEC_ARRAYS
from tolteca_simu.toltec.planning import ToltecPlanner

from .instrument import ToltecPanel
from .mapping import MappingPanel
from .results import ToltecResultsPanel, make_coverage_figure, make_sensitivity_tabs
from .site import LmtPanel
from .target import TargetPanel
from .trajectory import TrajectoryPanel, empty_figure, make_trajectory_figures
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
        Title, presets, limits, calibration data, and LMT and TolTEC settings.
    """

    def __init__(self, config: ObsPlannerConfig) -> None:
        super().__init__()
        self._toltec = ToltecPlanner(
            CalDataStore(config.cal_data_path),
            apt_path=config.toltec.apt,
            tel_surface_rms=config.lmt.tel_surface_rms,
            det_noise_factors=config.toltec.det_noise_factors,
        )
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
        self.site = controls.child(LmtPanel(config.lmt.tel_surface_rms))
        self.instrument = controls.child(ToltecPanel(self._toltec))
        self.mapping = controls.child(
            MappingPanel(
                MappingPresets.from_yaml(config.presets_path),
                t_exp_max=config.t_exp_max,
                instrument=self.instrument.instrument,
            )
        )
        self.visibility = results.child(
            VisibilityPanel(
                description=self.description, target_alt_min=config.target_alt_min
            )
        )
        self.trajectory = results.child(TrajectoryPanel())
        self.toltec_results = results.child(ToltecResultsPanel())

    def setup_callbacks(self, app: Dash) -> None:
        """Assemble the description and compute its trajectory and TolTEC results.

        Parameters
        ----------
        app : dash.Dash
            Application receiving the callbacks.
        """

        @app.callback(
            Output(self.description(), "data"),
            Input(self.target.target(), "data"),
            Input(self.mapping.mapping(), "data"),
            Input(self.site.site(), "data"),
            Input(self.instrument.instrument(), "data"),
        )
        def _make_description(
            target: dict | None,
            mapping: dict | None,
            site: dict | None,
            instrument: dict | None,
        ) -> dict[str, Any] | None:
            if target is None or mapping is None or site is None or instrument is None:
                return None
            description = ObservationDescription.model_validate(
                target | mapping | site | {"instrument": instrument}
            )
            return description.model_dump(mode="json")

        graphs = self.trajectory.graphs
        results = self.toltec_results

        @app.callback(
            [Output(graph(), "figure") for graph in graphs.values()],
            Output(results.coverage(), "figure"),
            Output(results.sensitivity(), "children"),
            Output(results.status(), "children"),
            Input(self.description(), "data"),
            Input(self.instrument.coverage_unit(), "value"),
            prevent_initial_call=True,
        )
        def _plan(data: dict | None, coverage_unit: str) -> list:
            if data is None:
                return [
                    *(empty_figure() for _ in graphs),
                    empty_figure(),
                    None,
                    "Complete the observation description.",
                ]
            description = ObservationDescription.model_validate(data)
            observer = get_lmt_observer()
            trajectory = get_trajectory(
                description.mapping,
                description.target,
                description.t0,
                t_exp=description.get_t_exp(),
                ref_frame=description.ref_frame,
                observer=observer,
            )
            result = self._toltec.plan(description, trajectory, observer)
            figures = make_trajectory_figures(
                trajectory,
                description.ref_frame,
                footprint=result.footprint,
                footprint_name=TOLTEC_ARRAYS[result.array_name].name_long,
            )
            status = (
                f"{TOLTEC_ARRAYS[result.array_name].name_long}, "
                f"{description.atm_model_name} atmosphere. "
                f"{result.n_passes} pass(es) reach the desired depth "
                f"of {description.desired_sens}."
            )
            return [
                *(figures[key] for key in graphs),
                make_coverage_figure(result, coverage_unit),
                make_sensitivity_tabs(result),
                status,
            ]
