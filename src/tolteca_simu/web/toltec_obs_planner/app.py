"""Planner page layout and application factory."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import dash
import dash_mantine_components as dmc
from dash import Dash, Input, Output, State, ctx, dcc
from dash_component_template import Template

from tolteca_simu.cal_data import CalDataStore
from tolteca_simu.config import FireflyViewerConfig
from tolteca_simu.core import Simu
from tolteca_simu.lmt import get_lmt_observer
from tolteca_simu.planning import MappingPresets, ObservationDescription, get_trajectory
from tolteca_simu.toltec import TOLTEC_ARRAYS
from tolteca_simu.toltec.planning import ToltecPlanner
from tolteca_simu.toltec.time_cost import get_time_cost

from .exports import ExportsPanel, make_downloads
from .instrument import ToltecPanel
from .mapping import MappingPanel
from .results import ToltecResultsPanel, make_sensitivity_tabs
from .site import LmtInfoPanel, LmtPanel
from .target import TargetPanel
from .trajectory import TrajectoryPanel, make_trajectory_figures
from .verify import VerifyPanel
from .views import make_view_description
from .views_aladin import AladinViewsPanel
from .views_firefly import FireflyViewsPanel
from .visibility import VisibilityPanel

if TYPE_CHECKING:
    from dash._callback import NoUpdate
    from tollan.config import RuntimeContext

    from tolteca_simu.config import ObsPlannerConfig
    from tolteca_simu.planning import Trajectory
    from tolteca_simu.toltec.planning import ToltecPlanningResult
    from tolteca_simu.toltec.time_cost import TimeCost

    from .views import ViewsPanel

__all__ = ["ObsPlanner", "create_app"]


def _now() -> datetime:
    return datetime.now(UTC)


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
    # The page loads the scripts of its viewer backend only.
    if isinstance(config.viewer, FireflyViewerConfig):
        external_scripts = [f"{config.viewer.url}firefly_loader.js"]
        assets_ignore = r"aladin_views\.js"
    else:
        external_scripts = []
        assets_ignore = r"firefly_views\.js"
    app = Dash(
        __name__,
        title=config.title,
        url_base_pathname=config.server.url_base_pathname,
        external_scripts=external_scripts,
        assets_ignore=assets_ignore,
    )
    app.layout = planner.layout()
    planner.register_callbacks(app)
    return app


class ObsPlanner(Template):
    """The planner page, organized as the v1 planner.

    The left column holds the Plan tab (target, site, instrument and mapping
    controls, and Execute) and the Verify tab (a saved result and Execute).
    The right column shows the results of the last Execute: the sky view, the
    downloads, the trajectory plots (collapsed), and the coverage view beside
    the sensitivity tables.

    The page keeps the observation description being edited, serialized as
    JSON, in its `description` store; Execute computes the results from it, or
    from the description loaded in the Verify tab. The files of each result
    are made once and kept in its `downloads` store, for the downloads and the
    coverage view.

    Parameters
    ----------
    config : tolteca_simu.config.ObsPlannerConfig
        Title, presets, limits, calibration data, viewer backend, and LMT and
        TolTEC settings.
    """

    def __init__(self, config: ObsPlannerConfig) -> None:
        super().__init__()
        self._apt_path = config.toltec.apt
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
        self.downloads = main.child[dcc.Store](data=None)
        # RA and Dec of the target the sky view centers on, in degrees.
        self.sky_target = main.child[dcc.Store](data=None)
        # As v1: controls in a fixed-width column, results fill the rest.
        body = main.child[dmc.Flex](
            direction={"base": "column", "md": "row"}, gap="md", align="flex-start"
        )
        controls = body.child[dmc.Box](w={"base": "100%", "md": 375}, flex="none")
        results = body.child[dmc.Box](w="100%", miw=0, flex=1)

        # Left column: the Plan and Verify tabs.
        tabs = controls.child[dmc.Tabs](value="plan", variant="pills")
        tab_list = tabs.child[dmc.TabsList](mb="sm")
        tab_list.child[dmc.TabsTab]("Plan", value="plan", size="xs")
        tab_list.child[dmc.TabsTab]("Verify", value="verify", size="xs")
        plan = tabs.child[dmc.TabsPanel](value="plan").child[dmc.Stack](gap="sm")
        self.target = plan.child(TargetPanel(target_alt_min=config.target_alt_min))
        self.visibility = self.target.footer.child(
            VisibilityPanel(
                description=self.description, target_alt_min=config.target_alt_min
            )
        )
        self.site_info = self.target.footer.child(LmtInfoPanel())
        self.site = plan.child(LmtPanel())
        self.instrument = plan.child(ToltecPanel(self._toltec))
        self.mapping = plan.child(
            MappingPanel(
                MappingPresets.from_yaml(config.presets_path),
                t_exp_max=config.t_exp_max,
                instrument=self.instrument.instrument,
            )
        )
        execute_row = self.mapping.footer.child[dmc.Group](justify="space-between")
        self._details_button = execute_row.child[dmc.Button](
            "Details ...", size="xs", variant="subtle"
        )
        # As v1, Execute turns red when it can run.
        self._execute = execute_row.child[dmc.Button](
            "Execute", size="xs", color="red", disabled=True
        )
        self._details = self.mapping.footer.child[dmc.Collapse](opened=False)
        self._details_text = self._details.child[dmc.Code]("N/A", block=True, fz="xs")
        self.verify = tabs.child[dmc.TabsPanel](value="verify").child(
            VerifyPanel(t_exp_max=config.t_exp_max, apt_path=config.toltec.apt)
        )

        # Right column, as in v1: sky view, downloads and the trajectory
        # toggle, trajectory plots, then coverage view beside the sensitivity.
        results = results.child[dmc.Stack](gap="md")
        sky = results.child[dmc.Box]()
        views_slot = results.child[dmc.Box]()
        downloads_row = results.child[dmc.Group](justify="space-between")
        self.exports = downloads_row.child(ExportsPanel(downloads=self.downloads))
        self._trajectory_button = downloads_row.child[dmc.Button](
            "Show trajectories in horizontal coordinates ...",
            size="xs",
            variant="subtle",
            disabled=True,
        )
        self._trajectory_collapse = results.child[dmc.Collapse](opened=False)
        self.trajectory = self._trajectory_collapse.child(TrajectoryPanel())
        bottom = results.child[dmc.SimpleGrid](cols={"base": 1, "lg": 2})
        coverage = bottom.child[dmc.Box]()
        self.toltec_results = bottom.child(ToltecResultsPanel())
        views: ViewsPanel
        if isinstance(config.viewer, FireflyViewerConfig):
            views = FireflyViewsPanel(
                config.viewer.url,
                sky_target=self.sky_target,
                downloads=self.downloads,
                sky_parent=sky,
                coverage_parent=coverage,
            )
        else:
            views = AladinViewsPanel(
                sky_target=self.sky_target,
                downloads=self.downloads,
                sky_parent=sky,
                coverage_parent=coverage,
            )
        self.views = views_slot.child(views)

    def _compute(
        self, description: ObservationDescription
    ) -> tuple[Trajectory, ToltecPlanningResult, TimeCost]:
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
        time_cost = get_time_cost(result.n_passes, result.t_exp, result.t_exp_eff)
        return trajectory, result, time_cost

    def _set_sky_target(
        self, resolved: dict | None, verify_data: dict | None
    ) -> list[float] | NoUpdate:
        # As v1: the sky view follows the target being edited, or the target
        # of a loaded results file.
        if ctx.triggered_id == self.verify.description().id:
            if verify_data is None:
                return dash.no_update
            target = ObservationDescription.model_validate(verify_data).target
            return [target.ra.degree, target.dec.degree]
        if resolved is None:
            return dash.no_update
        return [resolved["ra_deg"], resolved["dec_deg"]]

    def setup_callbacks(self, app: Dash) -> None:
        """Assemble the description, and compute its results on Execute.

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

        app.callback(
            Output(self.sky_target(), "data"),
            Input(self.target.resolved(), "data"),
            Input(self.verify.description(), "data"),
        )(self._set_sky_target)

        @app.callback(
            Output(self._execute(), "disabled"),
            Output(self._details_text(), "children"),
            Input(self.description(), "data"),
        )
        def _enable_execute(data: dict | None) -> tuple[bool, str]:
            if data is None:
                return True, "N/A"
            return False, json.dumps(data, indent=2)

        for button, collapse in (
            (self._details_button, self._details),
            (self._trajectory_button, self._trajectory_collapse),
        ):
            app.clientside_callback(
                "function(_n_clicks, opened) { return !opened; }",
                Output(collapse(), "opened"),
                Input(button(), "n_clicks"),
                State(collapse(), "opened"),
                prevent_initial_call=True,
            )

        graphs = self.trajectory.graphs
        results = self.toltec_results

        @app.callback(
            [Output(graph(), "figure") for graph in graphs.values()],
            Output(results.sensitivity(), "children"),
            Output(results.status(), "children"),
            Output(self.views.views(), "data"),
            Output(self.downloads(), "data"),
            Output(self._trajectory_button(), "disabled"),
            Input(self._execute(), "n_clicks"),
            Input(self.verify.execute(), "n_clicks"),
            State(self.description(), "data"),
            State(self.verify.description(), "data"),
            State(self.instrument.coverage_unit(), "value"),
            prevent_initial_call=True,
        )
        def _plan(
            _plan_clicks: int | None,
            _verify_clicks: int | None,
            plan_data: dict | None,
            verify_data: dict | None,
            coverage_unit: str,
        ) -> list:
            verifying = ctx.triggered_id == self.verify.execute().id
            data = verify_data if verifying else plan_data
            if data is None:
                return [dash.no_update] * (len(graphs) + 5)
            description = ObservationDescription.model_validate(data)
            trajectory, result, time_cost = self._compute(description)
            figures = make_trajectory_figures(
                trajectory,
                description.ref_frame,
                footprint=result.footprint,
                footprint_name=TOLTEC_ARRAYS[result.array_name].name_long,
            )
            status = (
                f"{'Verified result: ' if verifying else ''}"
                f"{TOLTEC_ARRAYS[result.array_name].name_long}, "
                f"{description.atm_model_name} atmosphere. "
                f"{result.n_passes} pass(es) reach the desired depth "
                f"of {description.desired_sens}."
            )
            downloads = make_downloads(
                description,
                result,
                time_cost,
                apt_path=self._apt_path,
                coverage_unit=coverage_unit,
                created_at=_now(),
            )
            return [
                *(figures[key] for key in graphs),
                make_sensitivity_tabs(result, time_cost),
                status,
                self.views.make_views(
                    make_view_description(
                        description.target, trajectory, result, coverage_unit
                    )
                ),
                downloads,
                False,
            ]
