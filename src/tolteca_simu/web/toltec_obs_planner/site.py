"""LMT observing conditions of the observation description, and site information."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import dash_mantine_components as dmc
from dash import Input, Output, State, dcc
from dash_component_template import Template

from tolteca_simu.lmt import get_lmt_observer

from .controls import labeled_choice

if TYPE_CHECKING:
    from dash import Dash

__all__ = ["LmtInfoPanel", "LmtPanel"]

_ATM_QUANTILES = [25, 50, 75]
_ATM_QUANTILE_DEFAULT = 25


class LmtPanel(Template):
    """Atmosphere conditions at the LMT.

    The panel publishes ``atm_model_name`` in its `site` store.
    """

    def __init__(self) -> None:
        super().__init__()
        card = self.child[dmc.Card](withBorder=True, padding="sm")
        stack = card.child[dmc.Stack](gap="xs")
        stack.child[dmc.Title]("Site: Large Millimeter Telescope", order=5)
        self._atm, _ = labeled_choice(
            stack,
            "Atm. Quantile",
            [{"label": f"{q} %", "value": str(q)} for q in _ATM_QUANTILES],
            str(_ATM_QUANTILE_DEFAULT),
        )
        self.site = stack.child[dcc.Store](data=None)

    def setup_callbacks(self, app: Dash) -> None:
        """Publish the atmosphere model.

        Parameters
        ----------
        app : dash.Dash
            Application receiving the callbacks.
        """
        app.clientside_callback(
            "function(q) { return {atm_model_name: 'am_q' + q}; }",
            Output(self.site(), "data"),
            Input(self._atm(), "value"),
        )


class LmtInfoPanel(Template):
    """Location of the LMT and its current UT, local and sidereal times.

    The times show, updated every half second, when the panel is expanded.
    """

    def __init__(self) -> None:
        super().__init__()
        observer = get_lmt_observer()
        location = observer.location
        self._info = {
            "lon": location.lon.degree,
            "timezone_local": observer.timezone.zone,
        }
        stack = self.child[dmc.Stack](gap=0)
        self._button = stack.child[dmc.Button](
            "Current Site Info ...",
            size="xs",
            variant="subtle",
            style={"alignSelf": "flex-start"},
        )
        self._collapse = stack.child[dmc.Collapse](opened=False)
        pre = {"ff": "monospace", "size": "xs", "style": {"whiteSpace": "pre"}}
        self._collapse.child[dmc.Text](
            f"Location: {location.lon.to_string()} {location.lat.to_string()}", **pre
        )
        self._times = self._collapse.child[dmc.Text](**pre)
        self._timer = stack.child[dcc.Interval](interval=500, disabled=True)

    def setup_callbacks(self, app: Dash) -> None:
        """Toggle the panel, and show the current times while it is open.

        Parameters
        ----------
        app : dash.Dash
            Application receiving the callbacks.
        """
        app.clientside_callback(
            "function(_n_clicks, opened) { return [!opened, opened]; }",
            Output(self._collapse(), "opened"),
            Output(self._timer(), "disabled"),
            Input(self._button(), "n_clicks"),
            State(self._collapse(), "opened"),
            prevent_initial_call=True,
        )
        app.clientside_callback(
            f"""
            function(_n_intervals) {{
                const info = {json.dumps(self._info)};
                const now = new Date();
                const format = (timeZone) => new Intl.DateTimeFormat("sv-SE", {{
                    timeZone, year: "numeric", month: "2-digit", day: "2-digit",
                    hour: "2-digit", minute: "2-digit", second: "2-digit",
                    hour12: false, timeZoneName: "short",
                }}).format(now);
                const lst = window.toltecObsPlanner.getLST(now, info.lon);
                const lstText = new Date(Math.floor(lst * 3600) * 1000)
                    .toISOString().slice(11, 19);
                return "Time: " + format("UTC") +
                    "\\nLocal Time: " + format(info.timezone_local) +
                    "\\nLST: " + lstText;
            }}
            """,
            Output(self._times(), "children"),
            Input(self._timer(), "n_intervals"),
            prevent_initial_call=True,
        )
