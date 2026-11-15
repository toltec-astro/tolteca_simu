"""Downloads of planning results."""

from __future__ import annotations

import base64
import gzip
from typing import TYPE_CHECKING, Any, Literal

import dash_mantine_components as dmc
from dash import ClientsideFunction, Input, Output, State, dcc
from dash_component_template import Template
from dash_iconify import DashIconify

from tolteca_simu.toltec.exports import make_export_files

from .controls import CONTROL_SIZE

if TYPE_CHECKING:
    from datetime import datetime

    from dash import Dash
    from dash_component_template import LazyComponent

    from tolteca_simu.toltec.planning import ObservationPlan

__all__ = ["ExportsPanel", "make_downloads"]


def make_downloads(
    plan: ObservationPlan,
    *,
    apt_path: str,
    coverage_unit: Literal["depth", "time"],
    created_at: datetime,
) -> dict[str, dict[str, Any]]:
    """Return the downloadable files of a plan.

    Parameters
    ----------
    plan : tolteca_simu.toltec.planning.ObservationPlan
        The planning results.
    apt_path : str
        APT path in the calibration store, recorded in the results table.
    coverage_unit : {"depth", "time"}
        Coverage map in mJy/beam or s/pixel.
    created_at : datetime.datetime
        Creation time recorded in the OT script and the results table.

    Returns
    -------
    dict
        ``lmtot`` (LMT OT script) and ``results`` (results ECSV) as data for
        `dash.dcc.Download`, and ``coverage``: the coverage FITS ``filename``
        and its gzip-compressed bytes, base64 encoded (``content_gzip``).
    """
    files = make_export_files(
        plan, apt_path=apt_path, coverage_unit=coverage_unit, created_at=created_at
    )
    coverage_name, coverage = files["coverage"]
    return {
        "lmtot": dcc.send_string(files["lmtot"][1], files["lmtot"][0]),
        "results": dcc.send_string(files["results"][1], files["results"][0]),
        # Compressed for the page; the download saves the FITS file itself.
        # Level 1: maps in s/pixel barely compress, and higher levels cost
        # seconds per result (2.1 s at the default level 9, 2 by 2 deg raster).
        "coverage": {
            "filename": coverage_name,
            "content_gzip": base64.b64encode(
                gzip.compress(coverage, compresslevel=1, mtime=0)
            ).decode(),
        },
    }


# The button label and color, and the tooltip of each download, as v1's.
_DOWNLOADS = {
    "lmtot": (
        "LMT OT Script",
        "blue",
        "Download LMT Observation Tool script to execute the observation at LMT.",
    ),
    "coverage": (
        "Coverage Map",
        "blue",
        (
            "Download the generated FITS (approximate) coverage image for the "
            "SINGLE observation (NOT COADDED)."
        ),
    ),
    "results": (
        "Export Results for Proposal Submission",
        "green",
        (
            "Export the current state and calculation results as ECSV table to be "
            "used for proposal submission."
        ),
    ),
}


class ExportsPanel(Template):
    """Download buttons for the files of the current result.

    The buttons save the files of the result in the page's `result` store,
    without a server request. As in v1, they are disabled until a result
    exists.

    Parameters
    ----------
    result : dash_component_template.LazyComponent
        Store holding the current result, whose ``downloads`` are the
        `make_downloads` files, or None.
    """

    def __init__(self, result: LazyComponent) -> None:
        super().__init__()
        self._result = result
        group = self.child[dmc.Group](gap="xs")
        buttons = {}
        for key, (label, color, tooltip) in _DOWNLOADS.items():
            buttons[key] = group.child[dmc.Tooltip](
                label=tooltip, multiline=True, w=280, withArrow=True
            ).child[dmc.Button](
                label,
                size=CONTROL_SIZE,
                color=color,
                leftSection=DashIconify(icon="tabler:download", width=16),
                disabled=True,
            )
        self.lmtot_button = buttons["lmtot"]
        self.coverage_button = buttons["coverage"]
        self.results_button = buttons["results"]
        self.lmtot_download = group.child[dcc.Download]()
        self.results_download = group.child[dcc.Download]()
        self.coverage_download = group.child[dcc.Download]()

    def setup_callbacks(self, app: Dash) -> None:
        """Enable the buttons for a result; save its files on click.

        Parameters
        ----------
        app : dash.Dash
            Application receiving the callbacks.
        """
        buttons = (self.lmtot_button, self.coverage_button, self.results_button)
        app.clientside_callback(
            "function(result) { return Array(3).fill(!result); }",
            [Output(button(), "disabled") for button in buttons],
            Input(self._result(), "data"),
        )
        for key, button, download in (
            ("lmtot", self.lmtot_button, self.lmtot_download),
            ("results", self.results_button, self.results_download),
        ):
            app.clientside_callback(
                f"""
                function(_n_clicks, result) {{
                    return result
                        ? result.downloads["{key}"]
                        : window.dash_clientside.no_update;
                }}
                """,
                Output(download(), "data"),
                Input(button(), "n_clicks"),
                State(self._result(), "data"),
                prevent_initial_call=True,
            )
        app.clientside_callback(
            ClientsideFunction(
                namespace="toltec_obs_planner", function_name="save_coverage"
            ),
            Output(self.coverage_download(), "data"),
            Input(self.coverage_button(), "n_clicks"),
            State(self._result(), "data"),
            prevent_initial_call=True,
        )
