"""Verification of a saved planning result."""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING, Any

import dash_mantine_components as dmc
from astropy.table import QTable
from astropy.time import Time
from dash import Input, Output, State, dcc
from dash_component_template import Template
from pydantic import ValidationError

from tolteca_simu.toltec.exports import read_results_metadata

from .controls import CONTROL_SIZE, titled_card

if TYPE_CHECKING:
    import astropy.units as u
    from dash import Dash

__all__ = ["VerifyPanel"]

# As v1: results files are small; larger uploads are rejected.
_UPLOAD_SIZE_MAX = 20_000


def _report(errors: list[str], details: str | None = None) -> list[Any]:
    # As v1: the errors as alerts, then the details of a loaded file.
    report: list[Any] = [dmc.Alert(message, color="red", p="xs") for message in errors]
    if details is not None:
        report.append(dmc.Code(details, block=True))
    return report


class VerifyPanel(Template):
    """Upload of a results file and Execute for the description it records.

    As in v1, the Details card lists what the file records, after alerts for
    a file that cannot be used or that was made with another APT. The panel
    publishes what the loaded file records in its `loaded` store: the
    observation ``description``, serialized as JSON, and the ``coverage_unit``
    of its coverage map. It enables its `execute` button, red, while a file is
    loaded.

    Parameters
    ----------
    t_exp_max : astropy.units.Quantity
        Longest pattern the planner accepts.
    apt_path : str
        APT the planner uses, compared with the one the file records.
    """

    def __init__(self, t_exp_max: u.Quantity, apt_path: str) -> None:
        super().__init__()
        self._t_exp_max = t_exp_max
        self._apt_path = apt_path
        stack = self.child[dmc.Stack](gap="md")
        _, upload_stack = titled_card(stack, "Upload Result to Verify")
        self._upload = upload_stack.child[dcc.Upload](
            dmc.Paper(
                dmc.Center(
                    dmc.Text(
                        [
                            "Drag and Drop or ",
                            dmc.Text("Select a File", span=True, c="blue"),
                        ],
                        size=CONTROL_SIZE,
                    ),
                    h=60,
                ),
                bd="1px dashed var(--mantine-color-default-border)",
                radius="sm",
            ),
            max_size=_UPLOAD_SIZE_MAX,
        )
        _, details_stack = titled_card(stack, "Details")
        self._details = details_stack.child[dmc.Stack](
            dmc.Code("...", block=True), gap="xs"
        )
        self.execute = details_stack.child[dmc.Group](justify="flex-end").child[
            dmc.Button
        ]("Execute", size=CONTROL_SIZE, disabled=True)
        self.loaded = stack.child[dcc.Store](data=None)

    def setup_callbacks(self, app: Dash) -> None:
        """Load the description recorded in an uploaded results file.

        Parameters
        ----------
        app : dash.Dash
            Application receiving the callbacks.
        """
        app.callback(
            Output(self.loaded(), "data"),
            Output(self._details(), "children"),
            Input(self._upload(), "contents"),
            State(self._upload(), "filename"),
            State(self._upload(), "last_modified"),
            prevent_initial_call=True,
        )(self._load)
        # As v1: Execute is enabled, red, while a file is loaded.
        app.clientside_callback(
            """
            function(loaded) {
                return loaded ? ["red", false] : ["blue", true];
            }
            """,
            Output(self.execute(), "color"),
            Output(self.execute(), "disabled"),
            Input(self.loaded(), "data"),
        )

    def _load(
        self, contents: str | None, filename: str | None, last_modified: float | None
    ) -> tuple:
        if contents is None:
            return None, _report([], "...")
        try:
            text = base64.b64decode(contents.split(",", 1)[1]).decode()
            table = QTable.read(text, format="ascii.ecsv")
        except (ValueError, UnicodeDecodeError):
            return None, _report(["Unable to parse the uploaded file."])
        try:
            description, meta = read_results_metadata(text)
        except (ValueError, ValidationError):
            return None, _report(["Invalid content in the file."])
        errors = []
        if meta.get("apt") != self._apt_path:
            errors.append(
                f"Mismatch APT version: {meta.get('apt')} != {self._apt_path}"
            )
        t_exp = description.get_t_exp()
        if t_exp > self._t_exp_max:
            errors.append(
                f"The pattern takes {t_exp:.2f} to finish, which exceeds the "
                f"required maximum value of {self._t_exp_max}."
            )
            return None, _report(errors)
        depths = "\n".join(
            f"    {name:<9}: {depth}"
            for name, depth in zip(
                table["array_name"], table["depth_rms_coadd_actual"], strict=True
            )
        )
        modified = (
            "N/A" if last_modified is None else Time(last_modified, format="unix").isot
        )
        instrument = description.instrument
        mapping = json.dumps(description.mapping.model_dump(mode="json"), indent=2)
        details = f"""\
ECSV_filename: {filename}
last_modified: {modified}
created_at   : {meta.get("created_at")}
version      : {meta.get("tolteca_simu_version")}
apt_name     : {meta.get("apt")}
instru_name  : {instrument.name}
polarized    : {instrument.polarized}
atm_mdl_name : {description.atm_model_name}
desired_sens : {description.desired_sens}
mapping      : {mapping}
t_exp        : {t_exp}
depth_rms_coadd_actual:
{depths}
proj_tot_time: {table["proj_total_time"][0]}"""
        loaded = {
            "description": description.model_dump(mode="json"),
            "coverage_unit": meta["coverage_unit"],
        }
        return loaded, _report(errors, details)
