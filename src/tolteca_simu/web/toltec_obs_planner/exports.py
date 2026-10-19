"""Downloads of planning results."""

from __future__ import annotations

import base64
import gzip
import io
import re
from typing import TYPE_CHECKING, Any

import dash_mantine_components as dmc
from dash import ClientsideFunction, Input, Output, State, dcc
from dash_component_template import Template

from tolteca_simu.lmtot import make_lmtot_script
from tolteca_simu.toltec.exports import (
    make_coverage_hdulist,
    make_results_table,
    write_results_ecsv,
)

if TYPE_CHECKING:
    from datetime import datetime

    from dash import Dash
    from dash_component_template import LazyComponent

    from tolteca_simu.planning import ObservationDescription
    from tolteca_simu.toltec.planning import ToltecPlanningResult
    from tolteca_simu.toltec.time_cost import TimeCost

__all__ = ["ExportsPanel", "make_downloads"]

# The job key of planner simulations, recorded as the OT script author (v1).
_JOB_KEY = "obs_planner_simu"


# Each file depends on the result and on the page's settings.
def make_downloads(  # noqa: PLR0913
    description: ObservationDescription,
    result: ToltecPlanningResult,
    time_cost: TimeCost,
    *,
    apt_path: str,
    coverage_unit: str,
    created_at: datetime,
) -> dict[str, dict[str, Any]]:
    """Return the downloadable files of a planning result.

    Parameters
    ----------
    description : tolteca_simu.planning.ObservationDescription
        The planned observation.
    result : tolteca_simu.toltec.planning.ToltecPlanningResult
        Its TolTEC results.
    time_cost : tolteca_simu.toltec.time_cost.TimeCost
        Its time cost.
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
    name = re.sub(r"\s+", "-", f"target_{description.target_name}")
    table = make_results_table(
        description, result, time_cost, apt_path, created_at=created_at
    )
    buffer = io.BytesIO()
    make_coverage_hdulist(result, coverage_unit).writeto(buffer)
    return {
        "lmtot": dcc.send_string(
            make_lmtot_script(description, author=_JOB_KEY, created_at=created_at),
            f"{name}.lmtot",
        ),
        "results": dcc.send_string(
            write_results_ecsv(table), "toltec_obs_planner_results.ecsv"
        ),
        # Compressed for the page; the download saves the FITS file itself.
        # Level 1: maps in s/pixel barely compress, and higher levels cost
        # seconds per result (2.1 s at the default level 9, 2 by 2 deg raster).
        "coverage": {
            "filename": f"obsplanner_toltec_{result.array_name}_cov.fits",
            "content_gzip": base64.b64encode(
                gzip.compress(buffer.getvalue(), compresslevel=1, mtime=0)
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
