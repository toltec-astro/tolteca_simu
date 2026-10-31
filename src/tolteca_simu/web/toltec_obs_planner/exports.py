"""Downloads of planning results."""

from __future__ import annotations

import base64
import gzip
from typing import TYPE_CHECKING, Any, Literal

import dash_mantine_components as dmc
from dash import ClientsideFunction, Input, Output, State, dcc
from dash_component_template import Template

from tolteca_simu.toltec.exports import make_export_files

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


class ExportsPanel(Template):
    """Download buttons for the files of the current result.

    The buttons save the files from the page's `downloads` store, without a
    server request.

    Parameters
    ----------
    downloads : dash_component_template.LazyComponent
        Store holding the `make_downloads` files of the current result, or None.
    """

    def __init__(self, downloads: LazyComponent) -> None:
        super().__init__()
        self._downloads = downloads
        group = self.child[dmc.Group](gap="xs")
        self.lmtot_button = group.child[dmc.Button](
            "LMT OT script", size="xs", variant="light"
        )
        self.coverage_button = group.child[dmc.Button](
            "Coverage map (FITS)", size="xs", variant="light"
        )
        self.results_button = group.child[dmc.Button](
            "Results for proposal (ECSV)", size="xs", color="green"
        )
        self.lmtot_download = group.child[dcc.Download]()
        self.results_download = group.child[dcc.Download]()
        self.coverage_download = group.child[dcc.Download]()

    def setup_callbacks(self, app: Dash) -> None:
        """Save each file of the current result when its button is clicked.

        Parameters
        ----------
        app : dash.Dash
            Application receiving the callbacks.
        """
        for key, button, download in (
            ("lmtot", self.lmtot_button, self.lmtot_download),
            ("results", self.results_button, self.results_download),
        ):
            app.clientside_callback(
                f"""
                function(_n_clicks, downloads) {{
                    return downloads
                        ? downloads["{key}"]
                        : window.dash_clientside.no_update;
                }}
                """,
                Output(download(), "data"),
                Input(button(), "n_clicks"),
                State(self._downloads(), "data"),
                prevent_initial_call=True,
            )
        app.clientside_callback(
            ClientsideFunction(
                namespace="toltec_obs_planner", function_name="save_coverage"
            ),
            Output(self.coverage_download(), "data"),
            Input(self.coverage_button(), "n_clicks"),
            State(self._downloads(), "data"),
            prevent_initial_call=True,
        )
