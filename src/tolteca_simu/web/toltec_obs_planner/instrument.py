"""TolTEC settings of the observation description."""

from __future__ import annotations

from typing import TYPE_CHECKING

import dash_mantine_components as dmc
from dash import Input, Output, dcc
from dash_component_template import Template

from tolteca_simu.toltec import TOLTEC_ARRAYS

if TYPE_CHECKING:
    from dash import Dash

    from tolteca_simu.toltec.planning import ToltecPlanner

__all__ = ["ToltecPanel"]

_NOTICE = (
    "The sensitivity and mapping speed estimates are based on commissioning data "
    "taken in December 2022 and are very uncertain. Use a healthy safety margin "
    "in the time requested."
)


class ToltecPanel(Template):
    """TolTEC Stokes parameters, band, and coverage display unit.

    The panel publishes the instrument settings of the observation description
    in its `instrument` store, and the display unit in its `coverage_unit`
    control.

    Parameters
    ----------
    planner : tolteca_simu.toltec.planning.ToltecPlanner
        The TolTEC planner, for the array property table in use.
    """

    def __init__(self, planner: ToltecPlanner) -> None:
        super().__init__()
        card = self.child[dmc.Card](withBorder=True, padding="md")
        stack = card.child[dmc.Stack](gap="sm")
        stack.child[dmc.Title]("Instrument: TolTEC", order=5)
        stack.child[dmc.Alert](_NOTICE, color="orange", title="Shared risks")
        n_dets = len(planner.apt)
        n_designed = sum(planner.n_dets_designed.values())
        stack.child[dmc.Text](
            f"APT version: {planner.apt.meta.get('version', 'designed')}. "
            f"Enabled detectors: {n_dets} / {n_designed} ({n_dets / n_designed:.0%}).",
            size="xs",
            c="dimmed",
        )
        stack.child[dmc.Text]("Stokes parameters", size="sm")
        self._stokes = stack.child[dmc.SegmentedControl](
            data=[
                {"label": "Total intensity (I)", "value": "I"},
                {"label": "Polarized (Q/U)", "value": "QU"},
            ],
            value="I",
            size="xs",
        )
        stack.child[dmc.Text]("Band", size="sm")
        self._band = stack.child[dmc.SegmentedControl](
            data=[
                {"label": f"{a.wl_center:g}", "value": name}
                for name, a in TOLTEC_ARRAYS.items()
            ],
            value="a1100",
            size="xs",
        )
        stack.child[dmc.Text]("Coverage unit", size="sm")
        self.coverage_unit = stack.child[dmc.SegmentedControl](
            data=[
                {"label": "mJy/beam", "value": "depth"},
                {"label": "s/pixel", "value": "time"},
            ],
            value="depth",
            size="xs",
        )
        self.instrument = stack.child[dcc.Store](data=None)

    def setup_callbacks(self, app: Dash) -> None:
        """Publish the instrument settings.

        Parameters
        ----------
        app : dash.Dash
            Application receiving the callbacks.
        """
        app.clientside_callback(
            """
            function(stokes, band) {
                return {name: "toltec", polarized: stokes === "QU", array_name: band};
            }
            """,
            Output(self.instrument(), "data"),
            Input(self._stokes(), "value"),
            Input(self._band(), "value"),
        )
