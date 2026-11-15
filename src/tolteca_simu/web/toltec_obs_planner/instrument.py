"""TolTEC settings of the observation description."""

from __future__ import annotations

from typing import TYPE_CHECKING

import dash_mantine_components as dmc
from dash import Input, Output, dcc
from dash_component_template import Template

from tolteca_simu.toltec import TOLTEC_ARRAYS, ToltecArrayName

from .controls import (
    CONTROL_SIZE,
    hover_card,
    labeled_choice,
    section_width,
    titled_card,
)

if TYPE_CHECKING:
    from dash import Dash
    from dash_component_template import LazyComponent

    from tolteca_simu.toltec.planning import ToltecPlanner

__all__ = ["ToltecPanel", "band_label"]

# v1 obs_planner toltec.py: the notice of shared risks and the polarimetry notes.
_README = [
    (
        "The TolTEC team has made its best guesses about the sensitivity and mapping "
        "speed of the instrument based on commissioning data taken in December, 2022."
    ),
    (
        "Users of this tool should be aware that these estimates are very uncertain. "
        "Users are encouraged to use a very healthy safety margin in their requested "
        "time when writing their proposals."
    ),
]
_POLARIMETRY_NOTES = [
    (
        "For polarimetry measurements, the relevant quantity is the 1-sigma "
        "uncertainty (error bar) in the polarized intensity. Here the polarized "
        "intensity is defined as the total intensity multiplied by the polarization "
        "fraction. Because of the need to separately measure Stokes Q and Stokes U, "
        "the integration time required to reach a given polarized intensity error bar "
        "is double that required to reach the same total intensity error bar. We "
        "apply an additional penalty due to imperfect polarization modulation (e.g., "
        "non-ideal behavior in the half-wave plate). This penalty is a factor of 10% "
        "in sensitivity (~20% in observing time)"
    ),
    "See:",
    (
        "A Primer on Far-Infrared Polarimetry, Hildebrand, R.H., et al. 2000, "
        "Publications of the Astronomical Society of the Pacific, 112, 1215."
    ),
]
_PLANCK_XIX_URL = "https://arxiv.org/pdf/1405.0871.pdf"
_LABELS = ["TolTEC band", "Coverage Unit"]


def band_label(array_name: ToltecArrayName) -> str:
    """Return the label of a TolTEC band: its center wavelength, as in v1.

    Parameters
    ----------
    array_name : {"a1100", "a1400", "a2000"}
        The array.

    Returns
    -------
    str
        The center wavelength with one decimal.

    Examples
    --------
    >>> band_label("a2000")
    '2.0 mm'
    """
    wl_center = TOLTEC_ARRAYS[array_name].wl_center
    return f"{wl_center.value:.1f} {wl_center.unit}"


def _add_notes(
    notes: LazyComponent, title: str, paragraphs: list[str]
) -> LazyComponent:
    notes.child[dmc.Text](title, size=CONTROL_SIZE, fw=700)
    for text in paragraphs:
        notes.child[dmc.Text](text, size=CONTROL_SIZE)
    return notes


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
        _, stack = titled_card(self, "Instrument: TolTEC")
        readme_target, readme_notes = hover_card(stack)
        _add_notes(readme_notes, "WARNING", _README)
        readme_target.child[dmc.Button](
            "README Before Use: Notice of Shared Risks",
            color="red",
            variant="outline",
            size=CONTROL_SIZE,
            fullWidth=True,
        )
        n_dets = len(planner.apt)
        n_designed = sum(planner.n_dets_designed.values())
        info = stack.child[dmc.Stack](gap=0)
        info.child[dmc.Text](
            f"APT version: {planner.apt.meta.get('version', 'designed')}",
            size=CONTROL_SIZE,
        )
        info.child[dmc.Text](
            f"Enabled detectors: {n_dets} / {n_designed} ({n_dets / n_designed:.0%})",
            size=CONTROL_SIZE,
        )
        width = section_width(_LABELS)
        stokes_target, stokes_notes = hover_card(stack)
        _add_notes(stokes_notes, "Notes on Polarimetry", _POLARIMETRY_NOTES).child[
            dmc.Text
        ](
            [
                "Appendix B.1 of Planck Intermediate Results XIX (",
                dmc.Anchor("link", href=_PLANCK_XIX_URL, target="_blank"),
                ")",
            ],
            size=CONTROL_SIZE,
        )
        self._stokes = labeled_choice(
            stokes_target,
            "Stokes Params",
            [
                {"label": "Total Intensity (I)", "value": "I"},
                {"label": "Polarized Emission (Q/U)", "value": "QU"},
            ],
            "I",
            below=True,
        )
        self._band = labeled_choice(
            stack,
            "TolTEC band",
            [{"label": band_label(name), "value": name} for name in TOLTEC_ARRAYS],
            "a1100",
            label_width=width,
        )
        self.coverage_unit = labeled_choice(
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
