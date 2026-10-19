"""TolTEC settings of the observation description."""

from __future__ import annotations

from typing import TYPE_CHECKING

import dash_mantine_components as dmc
from dash import Input, Output, dcc
from dash_component_template import Template

from tolteca_simu.toltec import TOLTEC_ARRAYS

from .controls import labeled_choice, section_width

if TYPE_CHECKING:
    from dash import Dash
    from dash_component_template import LazyComponent

    from tolteca_simu.toltec.planning import ToltecPlanner

__all__ = ["ToltecPanel"]

# v1 obs_planner toltec.py: the notice of shared risks and the polarimetry notes.
_README = """
**WARNING**

The TolTEC team has made its best guesses about the sensitivity and mapping
speed of the instrument based on commissioning data taken in December, 2022.

Users of this tool should be aware that these estimates are very uncertain.
Users are encouraged to use a very healthy safety margin in their requested
time when writing their proposals.
"""
_POLARIMETRY_NOTES = """
**Notes on Polarimetry**

For polarimetry measurements, the relevant quantity is the 1-sigma uncertainty
(error bar) in the polarized intensity. Here the polarized intensity is defined
as the total intensity multiplied by the polarization fraction. Because of the
need to separately measure Stokes Q and Stokes U, the integration time required
to reach a given polarized intensity error bar is double that required to reach
the same total intensity error bar. We apply an additional penalty due to
imperfect polarization modulation (e.g., non-ideal behavior in the half-wave
plate). This penalty is a factor of 10% in sensitivity (~20% in observing
time)

See:

A Primer on Far-Infrared Polarimetry, Hildebrand, R.H., et al. 2000,
Publications of the Astronomical Society of the Pacific, 112, 1215.

Appendix B.1 of Planck Intermediate Results XIX
([link](https://arxiv.org/pdf/1405.0871.pdf))
"""
_LABELS = ["Stokes Params", "TolTEC band", "Coverage Unit"]


def _hover_card(parent: LazyComponent, notes: str) -> LazyComponent:
    card = parent.child[dmc.HoverCard](
        width=360, shadow="md", withArrow=True, position="bottom-start"
    )
    target = card.child[dmc.HoverCardTarget](boxWrapperProps={"w": "100%"})
    card.child[dmc.HoverCardDropdown]().child[dcc.Markdown](
        notes, link_target="_blank", style={"fontSize": "var(--mantine-font-size-xs)"}
    )
    return target


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
        card = self.child[dmc.Card](withBorder=True, padding="sm")
        stack = card.child[dmc.Stack](gap="xs")
        stack.child[dmc.Title]("Instrument: TolTEC", order=5)
        _hover_card(stack, _README).child[dmc.Button](
            "README Before Use: Notice of Shared Risks",
            color="red",
            variant="outline",
            size="xs",
            fullWidth=True,
        )
        n_dets = len(planner.apt)
        n_designed = sum(planner.n_dets_designed.values())
        info = stack.child[dmc.Stack](gap=0, pl=8)
        info.child[dmc.Text](
            f"APT version: {planner.apt.meta.get('version', 'designed')}", size="xs"
        )
        info.child[dmc.Text](
            f"Enabled detectors: {n_dets} / {n_designed} ({n_dets / n_designed:.0%})",
            size="xs",
        )
        width = section_width(_LABELS)
        self._stokes, _ = labeled_choice(
            _hover_card(stack, _POLARIMETRY_NOTES),
            "Stokes Params",
            [
                {"label": "Total Intensity (I)", "value": "I"},
                {"label": "Polarized Emission (Q/U)", "value": "QU"},
            ],
            "I",
            label_width=width,
        )
        self._band, _ = labeled_choice(
            stack,
            "TolTEC band",
            [
                {"label": f"{a.wl_center:g}", "value": name}
                for name, a in TOLTEC_ARRAYS.items()
            ],
            "a1100",
            label_width=width,
        )
        self.coverage_unit, _ = labeled_choice(
            stack,
            "Coverage Unit",
            [
                {"label": "mJy/beam", "value": "depth"},
                {"label": "s/pixel", "value": "time"},
            ],
            "depth",
            label_width=width,
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
