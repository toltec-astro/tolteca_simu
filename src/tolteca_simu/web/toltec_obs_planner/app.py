"""Planner page layout and application factory."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

import astropy.units as u
import dash
import dash_mantine_components as dmc
from astropy.coordinates import SkyCoord
from astropy.time import Time
from dash import Dash, Input, Output, State, ctx, dcc
from dash_component_template import Template

from tolteca_simu.config import FireflyViewerConfig
from tolteca_simu.core import Simu
from tolteca_simu.lmt import get_lmt_observer
from tolteca_simu.planning import (
    MappingPresets,
    ObservationDescription,
    get_target_visibility,
)
from tolteca_simu.toltec import TOLTEC_ARRAYS
from tolteca_simu.toltec.planning import ToltecPlanner, plan_observation

from .controls import CONTROL_SIZE
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
from .visibility import make_visibility_figure

if TYPE_CHECKING:
    from dash._callback import NoUpdate
    from dash_component_template import LazyComponent
    from tollan.config import RuntimeContext

    from tolteca_simu.config import ObsPlannerConfig

    from .views import ViewsPanel

__all__ = ["ObsPlanner", "create_app"]


def _now() -> datetime:
    return datetime.now(UTC)


def _load_earth_orientation() -> None:
    # Positions at the LMT need astropy's Earth orientation (IERS) table. On
    # first use astropy reads it and, when stale, downloads a new one; that
    # takes seconds, so it is done here rather than in an observer's request.
    origin = SkyCoord(0 * u.deg, 0 * u.deg)
    origin.transform_to(get_lmt_observer().altaz(time=Time.now()))


def create_app(runtime: RuntimeContext) -> Dash:
    """Create the planner from the ``simu.obs_planner`` settings.

    The Earth orientation data for time-dependent computations are loaded
    here, refreshing astropy's table if it is stale, so that the first request
    does not wait for them. Processes forked from this one, such as gunicorn
    workers, share them.

    Parameters
    ----------
    runtime : tollan.config.RuntimeContext
        Runtime supplying the ``simu`` settings.

    Returns
    -------
    dash.Dash
        Application with its layout and callbacks; no server is started.
    """
    simu = Simu(runtime)
    config = simu.config.obs_planner
    _load_earth_orientation()
    planner = ObsPlanner(config, simu.make_toltec_planner())
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
    The right column shows the results of the last Execute: the sky view with
    the legend of its overlays, the downloads, the target altitude and
    trajectory plots (collapsed), and the coverage view beside the sensitivity
    tables. While Execute computes, the results show a loading overlay.

    As in v1, each panel assembles its part of the observation description in
    the browser, and Execute is enabled, red, once all parts are valid.
    Execute computes the result on the server and keeps it in the page's
    `result` store: the figures, tables, view data, the files for the
    downloads and the coverage view, and the description it was computed
    from; the page draws everything from that store in the browser.

    Parameters
    ----------
    config : tolteca_simu.config.ObsPlannerConfig
        Title, presets, limits, viewer backend, and the array property table
        recorded in results.
    toltec_planner : tolteca_simu.toltec.planning.ToltecPlanner
        The planner that computes results, as built by
        `tolteca_simu.core.Simu.make_toltec_planner`.
    """

    def __init__(self, config: ObsPlannerConfig, toltec_planner: ToltecPlanner) -> None:
        super().__init__()
        self._apt_path = config.toltec.apt
        self._toltec = toltec_planner
        self._target_alt_min = config.target_alt_min
        page = self.child[dmc.MantineProvider]().child[dmc.Box](px="md", pb="md")
        # As v1: the title with the subtitle after it, above a rule.
        header = page.child[dmc.Group](gap="sm", align="baseline", py="xs")
        header.child[dmc.Title](config.title, order=2)
        header.child[dmc.Text](config.subtitle, c="dimmed")
        page.child[dmc.Divider](mb="md")
        self.result = page.child[dcc.Store](data=None)
        # RA and Dec of the target the sky view centers on, in degrees.
        self.sky_target = page.child[dcc.Store](data=None)
        # As v1: controls in a fixed-width column, results fill the rest.
        body = page.child[dmc.Flex](
            direction={"base": "column", "md": "row"}, gap="md", align="flex-start"
        )
        controls = body.child[dmc.Box](w={"base": "100%", "md": 375}, flex="none")
        results = body.child[dmc.Box](w="100%", miw=0, flex=1)

        # Left column: the Plan and Verify tabs.
        tabs = controls.child[dmc.Tabs](value="plan", variant="pills")
        tab_list = tabs.child[dmc.TabsList](mb="sm")
        tab_list.child[dmc.TabsTab]("Plan", value="plan", size=CONTROL_SIZE)
        tab_list.child[dmc.TabsTab]("Verify", value="verify", size=CONTROL_SIZE)
        plan = tabs.child[dmc.TabsPanel](value="plan").child[dmc.Stack](gap="sm")
        self.target = plan.child(TargetPanel(target_alt_min=config.target_alt_min))
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
            "Details ...", size=CONTROL_SIZE, variant="subtle"
        )
        self._execute = execute_row.child[dmc.Button](
            "Execute", size=CONTROL_SIZE, disabled=True
        )
        self._details = self.mapping.footer.child[dmc.Collapse](opened=False)
        self._details_text = self._details.child[dmc.Code]("N/A", block=True)
        self.verify = tabs.child[dmc.TabsPanel](value="verify").child(
            VerifyPanel(t_exp_max=config.t_exp_max, apt_path=config.toltec.apt)
        )

        self._add_results(results.child[dmc.Stack](gap="sm"), config)

    def _add_results(self, results: LazyComponent, config: ObsPlannerConfig) -> None:
        # Right column, as in v1: sky view, downloads and the trajectory
        # toggle, trajectory plots, then coverage view beside the sensitivity.
        # As v1's spinners, each block shows a loading overlay during Execute.
        sky = results.child[dmc.Box](pos="relative")
        views_slot = results.child[dmc.Box]()
        downloads_row = results.child[dmc.Group](justify="space-between")
        self.exports = downloads_row.child(ExportsPanel(result=self.result))
        self._trajectory_button = downloads_row.child[dmc.Button](
            "Show Trajs in Horizontal Coords...",
            size=CONTROL_SIZE,
            variant="subtle",
            disabled=True,
        )
        self._trajectory_collapse = results.child[dmc.Collapse](opened=False)
        trajectory = self._trajectory_collapse.child[dmc.Box](pos="relative")
        self.trajectory = trajectory.child(TrajectoryPanel())
        bottom = results.child[dmc.SimpleGrid](cols={"base": 1, "lg": 2})
        coverage = bottom.child[dmc.Box](pos="relative")
        sensitivity = bottom.child[dmc.Box](pos="relative")
        self.toltec_results = sensitivity.child(ToltecResultsPanel())
        self._busy = [
            parent.child[dmc.LoadingOverlay](visible=False, zIndex=10)
            for parent in (sky, trajectory, coverage, sensitivity)
        ]
        views: ViewsPanel
        if isinstance(config.viewer, FireflyViewerConfig):
            views = FireflyViewsPanel(
                config.viewer.url,
                sky_target=self.sky_target,
                result=self.result,
                sky_parent=sky,
                coverage_parent=coverage,
            )
        else:
            views = AladinViewsPanel(
                sky_target=self.sky_target,
                result=self.result,
                sky_parent=sky,
                coverage_parent=coverage,
            )
        self.views = views_slot.child(views)

    def _set_sky_target(
        self, resolved: dict | None, loaded: dict | None
    ) -> list[float] | NoUpdate:
        # As v1: the sky view follows the target being edited, or the target
        # of a loaded results file.
        if ctx.triggered_id == self.verify.loaded().id:
            if loaded is None:
                return dash.no_update
            description = ObservationDescription.model_validate(loaded["description"])
            target = description.target
            return [target.ra.degree, target.dec.degree]
        if resolved is None:
            return dash.no_update
        return [resolved["ra_deg"], resolved["dec_deg"]]

    def setup_callbacks(self, app: Dash) -> None:
        """Enable Execute, compute its result, and draw the result.

        Parameters
        ----------
        app : dash.Dash
            Application receiving the callbacks.
        """
        app.callback(
            Output(self.sky_target(), "data"),
            Input(self.target.resolved(), "data"),
            Input(self.verify.loaded(), "data"),
        )(self._set_sky_target)
        # As v1: Execute is enabled, red, once the mapping and the target are
        # valid.
        app.clientside_callback(
            """
            function(presetError, mapping, target) {
                if (presetError || !mapping || !target) {
                    return ["blue", true];
                }
                return ["red", false];
            }
            """,
            Output(self._execute(), "color"),
            Output(self._execute(), "disabled"),
            Input(self.mapping.preset_select(), "error"),
            Input(self.mapping.mapping(), "data"),
            Input(self.target.target(), "data"),
        )
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
        app.callback(
            Output(self.result(), "data"),
            Input(self._execute(), "n_clicks"),
            Input(self.verify.execute(), "n_clicks"),
            State(self.target.target(), "data"),
            State(self.mapping.mapping(), "data"),
            State(self.site.site(), "data"),
            State(self.instrument.instrument(), "data"),
            State(self.verify.loaded(), "data"),
            State(self.instrument.coverage_unit(), "value"),
            # As v1's spinners: the Execute buttons show that results are
            # being computed, and take no second click meanwhile; the results
            # they will replace are covered.
            running=[
                (Output(self._execute(), "loading"), True, False),
                (Output(self.verify.execute(), "loading"), True, False),
                *((Output(busy(), "visible"), True, False) for busy in self._busy),
            ],
            prevent_initial_call=True,
        )(self._plan)
        # As v1: the page draws the result from its store in the browser.
        graphs = self.trajectory.graphs
        app.clientside_callback(
            f"""
            function(result) {{
                const noUpdate = window.dash_clientside.no_update;
                if (!result) {{
                    return Array({len(graphs) + 4}).fill(noUpdate);
                }}
                return [
                    ...{json.dumps(list(graphs))}.map(key => result.figures[key]),
                    result.sensitivity,
                    result.legend,
                    JSON.stringify(result.description, null, 2),
                    false,
                ];
            }}
            """,
            [Output(graph(), "figure") for graph in graphs.values()],
            Output(self.toltec_results.sensitivity(), "children"),
            Output(self.views.legend(), "children"),
            Output(self._details_text(), "children"),
            Output(self._trajectory_button(), "disabled"),
            Input(self.result(), "data"),
        )

    def _plan(  # noqa: PLR0913, PLR0917
        self,
        _plan_clicks: int | None,
        _verify_clicks: int | None,
        target: dict | None,
        mapping: dict | None,
        site: dict | None,
        instrument: dict | None,
        loaded: dict | None,
        coverage_unit: Literal["depth", "time"],
    ) -> dict[str, Any] | NoUpdate:
        # As v1: a loaded results file is executed in the coverage unit it
        # records; the Plan tab uses the instrument settings.
        if ctx.triggered_id == self.verify.execute().id:
            if loaded is None:
                return dash.no_update
            description = ObservationDescription.model_validate(loaded["description"])
            coverage_unit = loaded["coverage_unit"]
        else:
            if target is None or mapping is None or site is None or instrument is None:
                return dash.no_update
            description = ObservationDescription.model_validate(
                target | mapping | site | {"instrument": instrument}
            )
        plan = plan_observation(description, self._toltec)
        trajectory, result = plan.trajectory, plan.result
        figures = make_trajectory_figures(
            trajectory,
            description.ref_frame,
            footprint=result.footprint,
            footprint_name=TOLTEC_ARRAYS[result.array_name].name_long,
        )
        figures["visibility"] = make_visibility_figure(
            get_target_visibility(
                description.target, description.t0, get_lmt_observer()
            ),
            description.t0 + description.get_t_exp(),
            self._target_alt_min,
        )
        view_description = make_view_description(
            description.target, trajectory, result, coverage_unit
        )
        return {
            "figures": figures,
            "sensitivity": make_sensitivity_tabs(result, plan.time_cost),
            "legend": self.views.make_legend(view_description),
            "views": self.views.make_views(view_description),
            "downloads": make_downloads(
                plan,
                apt_path=self._apt_path,
                coverage_unit=coverage_unit,
                created_at=_now(),
            ),
            "description": description.model_dump(mode="json"),
        }
