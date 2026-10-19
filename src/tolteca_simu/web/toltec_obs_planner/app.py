"""Planner page layout and application factory."""

from __future__ import annotations

import base64
import io
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import dash
import dash_mantine_components as dmc
from dash import Dash, Input, Output, State, dcc
from dash_component_template import Template
from pydantic import ValidationError

from tolteca_simu.cal_data import CalDataStore
from tolteca_simu.core import Simu
from tolteca_simu.lmt import get_lmt_observer
from tolteca_simu.lmtot import make_lmtot_script
from tolteca_simu.planning import MappingPresets, ObservationDescription, get_trajectory
from tolteca_simu.toltec import TOLTEC_ARRAYS
from tolteca_simu.toltec.exports import (
    make_coverage_hdulist,
    make_results_table,
    read_results_metadata,
    write_results_ecsv,
)
from tolteca_simu.toltec.planning import ToltecPlanner
from tolteca_simu.toltec.time_cost import get_time_cost

from .exports import ExportsPanel
from .instrument import ToltecPanel
from .mapping import MappingPanel
from .results import ToltecResultsPanel, make_coverage_figure, make_sensitivity_tabs
from .site import LmtPanel
from .sky import SkyViewPanel, make_sky_view
from .target import TargetPanel
from .trajectory import TrajectoryPanel, empty_figure, make_trajectory_figures
from .visibility import VisibilityPanel

if TYPE_CHECKING:
    from tollan.config import RuntimeContext

    from tolteca_simu.config import ObsPlannerConfig
    from tolteca_simu.planning import Trajectory
    from tolteca_simu.toltec.planning import ToltecPlanningResult
    from tolteca_simu.toltec.time_cost import TimeCost

__all__ = ["ObsPlanner", "create_app"]

# The job key of planner simulations, recorded as the OT script author (v1).
_JOB_KEY = "obs_planner_simu"


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
    app = Dash(
        __name__,
        title=config.title,
        url_base_pathname=config.server.url_base_pathname,
    )
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
        self._apt_path = config.toltec.apt
        self._t_exp_max = config.t_exp_max
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
        self.sky = results.child(SkyViewPanel())
        self.toltec_results = results.child(ToltecResultsPanel())
        self.exports = results.child(ExportsPanel())

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
            Output(self.sky.viewer(), "target"),
            Output(self.sky.viewer(), "fov"),
            Output(self.sky.viewer(), "layers"),
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
                    dash.no_update,
                    dash.no_update,
                    [],
                ]
            description = ObservationDescription.model_validate(data)
            trajectory, result, time_cost = self._compute(description)
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
                make_sensitivity_tabs(result, time_cost),
                status,
                *make_sky_view(description.target, trajectory, result, coverage_unit),
            ]

        self._setup_download_callbacks(app)
        self._setup_upload_callback(app)

    def _setup_download_callbacks(self, app: Dash) -> None:
        exports = self.exports

        @app.callback(
            Output(exports.lmtot_download(), "data"),
            Input(exports.lmtot_button(), "n_clicks"),
            State(self.description(), "data"),
            prevent_initial_call=True,
        )
        def _download_lmtot(_n_clicks: int, data: dict | None) -> dict | None:
            if data is None:
                return None
            description = ObservationDescription.model_validate(data)
            name = re.sub(r"\s+", "-", f"target_{description.target_name}")
            return dcc.send_string(
                make_lmtot_script(description, author=_JOB_KEY, created_at=_now()),
                f"{name}.lmtot",
            )

        @app.callback(
            Output(exports.results_download(), "data"),
            Input(exports.results_button(), "n_clicks"),
            State(self.description(), "data"),
            prevent_initial_call=True,
        )
        def _download_results(_n_clicks: int, data: dict | None) -> dict | None:
            if data is None:
                return None
            description = ObservationDescription.model_validate(data)
            _, result, time_cost = self._compute(description)
            table = make_results_table(
                description, result, time_cost, self._apt_path, created_at=_now()
            )
            return dcc.send_string(
                write_results_ecsv(table), "toltec_obs_planner_results.ecsv"
            )

        @app.callback(
            Output(exports.coverage_download(), "data"),
            Input(exports.coverage_button(), "n_clicks"),
            State(self.description(), "data"),
            State(self.instrument.coverage_unit(), "value"),
            prevent_initial_call=True,
        )
        def _download_coverage(
            _n_clicks: int, data: dict | None, coverage_unit: str
        ) -> dict | None:
            if data is None:
                return None
            description = ObservationDescription.model_validate(data)
            _, result, _ = self._compute(description)
            buffer = io.BytesIO()
            make_coverage_hdulist(result, coverage_unit).writeto(buffer)
            return dcc.send_bytes(
                buffer.getvalue(), f"obsplanner_toltec_{result.array_name}_cov.fits"
            )

    def _setup_upload_callback(self, app: Dash) -> None:
        exports = self.exports

        @app.callback(
            Output(self.description(), "data", allow_duplicate=True),
            Output(exports.status(), "children"),
            Input(exports.upload(), "contents"),
            State(exports.upload(), "filename"),
            prevent_initial_call=True,
        )
        def _load_results(contents: str | None, filename: str | None) -> tuple:
            if contents is None:
                return None, ""
            try:
                text = base64.b64decode(contents.split(",", 1)[1]).decode()
                description, meta = read_results_metadata(text)
            except (ValueError, ValidationError, UnicodeDecodeError) as error:
                return dash.no_update, f"Unable to load {filename}: {error}"
            t_exp = description.get_t_exp()
            if t_exp > self._t_exp_max:
                message = (
                    f"{filename}: the pattern takes {t_exp:.2f}, longer than the "
                    f"maximum of {self._t_exp_max}."
                )
                return dash.no_update, message
            notes = [f"Loaded {filename}, created {meta.get('created_at')}."]
            if meta.get("apt") != self._apt_path:
                notes.append(
                    f"It used APT {meta.get('apt')}; results now use {self._apt_path}."
                )
            notes.append("Editing any control replaces the loaded description.")
            return description.model_dump(mode="json"), " ".join(notes)
