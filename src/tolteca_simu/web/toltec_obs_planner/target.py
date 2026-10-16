"""Target and start time of the observation description."""

from __future__ import annotations

from typing import TYPE_CHECKING

import dash_mantine_components as dmc
from astropy.time import Time
from dash import Input, Output, State, dcc
from dash_component_template import Template
from pydantic import ValidationError

from tolteca_simu.planning import parse_target

if TYPE_CHECKING:
    from dash import Dash

__all__ = ["TargetPanel"]


class TargetPanel(Template):
    """Inputs for the target and the observation start time.

    The panel publishes the target part of the observation description,
    serialized as JSON, in its `target` store: ``target_name``, ``target`` and
    ``t0``. The store holds None while an input is invalid.
    """

    def __init__(self) -> None:
        super().__init__()
        card = self.child[dmc.Card](withBorder=True, padding="md")
        stack = card.child[dmc.Stack](gap="sm")
        stack.child[dmc.Title]("Target", order=5)
        self._target_input = stack.child[dmc.TextInput](
            label="Target name or coordinate",
            description="Names are resolved by a lookup service.",
            placeholder="M1, NGC 1277, 17.7d -2.1d, 10h09m08s +20d19m18s",
            value="M1",
            debounce=True,
        )
        self._target_status = stack.child[dmc.Text](size="xs", c="dimmed")
        self._date_input = stack.child[dmc.DateInput](
            label="Observation date (UT)", valueFormat="YYYY-MM-DD", value=None
        )
        self._time_input = stack.child[dmc.TimeInput](
            label="Start time (UT)", withSeconds=True, value="06:00:00"
        )
        self._resolved = stack.child[dcc.Store](data=None)
        self.target = stack.child[dcc.Store](data=None)

    def setup_callbacks(self, app: Dash) -> None:
        """Resolve the target and publish it with the start time.

        Parameters
        ----------
        app : dash.Dash
            Application receiving the callbacks.
        """
        app.clientside_callback(
            """
            function(_id, value) {
                return value || new Date().toISOString().slice(0, 10);
            }
            """,
            Output(self._date_input(), "value"),
            Input(self._date_input(), "id"),
            State(self._date_input(), "value"),
        )

        @app.callback(
            Output(self._resolved(), "data"),
            Output(self._target_input(), "error"),
            Output(self._target_status(), "children"),
            Input(self._target_input(), "value"),
        )
        def _resolve_target(
            text: str | None,
        ) -> tuple[dict[str, str] | None, str | None, str]:
            if not text:
                return None, "Enter a target name or coordinate.", ""
            try:
                coord = parse_target(text)
            except ValidationError:
                return None, f"Unable to resolve {text!r}.", ""
            ra, dec = coord.ra.degree, coord.dec.degree
            status = f"Resolved to {ra:.6f}d {dec:.6f}d (ICRS)."
            return {"name": text, "coord": f"{ra:.17g}d {dec:.17g}d"}, None, status

        @app.callback(
            Output(self.target(), "data"),
            Output(self._time_input(), "error"),
            Input(self._resolved(), "data"),
            Input(self._date_input(), "value"),
            Input(self._time_input(), "value"),
        )
        def _make_target(
            resolved: dict[str, str] | None, date: str | None, time: str
        ) -> tuple[dict[str, str] | None, str | None]:
            if resolved is None or not date:
                return None, None
            try:
                t0 = Time(f"{date} {time}", scale="utc")
            except ValueError:
                return None, "Use HH:MM:SS."
            return {
                "target_name": resolved["name"],
                "target": resolved["coord"],
                "t0": t0.isot,
            }, None
