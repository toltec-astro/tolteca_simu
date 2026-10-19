"""Verification of a saved planning result."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

import dash_mantine_components as dmc
from dash import Input, Output, State, dcc, html
from dash_component_template import Template
from pydantic import ValidationError

from tolteca_simu.toltec.exports import read_results_metadata

if TYPE_CHECKING:
    import astropy.units as u
    from dash import Dash

__all__ = ["VerifyPanel"]


class VerifyPanel(Template):
    """Upload of a results file and Execute for the description it records.

    The panel publishes the loaded observation description, serialized as
    JSON, in its `description` store, and enables its `execute` button.

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
        upload_card = stack.child[dmc.Card](withBorder=True, padding="sm")
        upload_stack = upload_card.child[dmc.Stack](gap="sm")
        upload_stack.child[dmc.Title]("Upload result to verify", order=5)
        self._upload = upload_stack.child[dcc.Upload](
            html.Div("Drop a results ECSV file here, or click to select one."),
            max_size=1_000_000,
            style={
                "border": "1px dashed var(--mantine-color-gray-5)",
                "borderRadius": "4px",
                "padding": "12px",
                "textAlign": "center",
                "fontSize": "12px",
            },
        )
        details_card = stack.child[dmc.Card](withBorder=True, padding="sm")
        details_stack = details_card.child[dmc.Stack](gap="sm")
        details_stack.child[dmc.Title]("Details", order=5)
        self._details = details_stack.child[dmc.Text](
            "No file loaded.", size="xs", c="dimmed"
        )
        self.execute = details_stack.child[dmc.Group](justify="flex-end").child[
            dmc.Button
        ]("Execute", size="xs", color="red", disabled=True)
        self.description = stack.child[dcc.Store](data=None)

    def setup_callbacks(self, app: Dash) -> None:
        """Load the description recorded in an uploaded results file.

        Parameters
        ----------
        app : dash.Dash
            Application receiving the callbacks.
        """

        @app.callback(
            Output(self.description(), "data"),
            Output(self._details(), "children"),
            Output(self.execute(), "disabled"),
            Input(self._upload(), "contents"),
            State(self._upload(), "filename"),
            prevent_initial_call=True,
        )
        def _load(contents: str | None, filename: str | None) -> tuple:
            if contents is None:
                return None, "No file loaded.", True
            try:
                text = base64.b64decode(contents.split(",", 1)[1]).decode()
                description, meta = read_results_metadata(text)
            except (ValueError, ValidationError, UnicodeDecodeError) as error:
                return None, f"Unable to load {filename}: {error}", True
            t_exp = description.get_t_exp()
            if t_exp > self._t_exp_max:
                message = (
                    f"{filename}: the pattern takes {t_exp:.2f}, longer than the "
                    f"maximum of {self._t_exp_max}."
                )
                return None, message, True
            loaded = (
                f"Loaded {filename}, created {meta.get('created_at')}: "
                f"{description.target_name}, {description.t0.iso[:19]} UT."
            )
            notes = [loaded]
            if meta.get("apt") != self._apt_path:
                notes.append(
                    f"It used APT {meta.get('apt')}; results now use {self._apt_path}."
                )
            notes.append("Press Execute to show its results.")
            return description.model_dump(mode="json"), " ".join(notes), False
