"""LMT observing conditions of the observation description."""

from __future__ import annotations

from typing import TYPE_CHECKING

import astropy.units as u
import dash_mantine_components as dmc
from dash import Input, Output, dcc
from dash_component_template import Template

if TYPE_CHECKING:
    from dash import Dash

__all__ = ["LmtPanel"]

_ATM_QUANTILES = [25, 50, 75]
_ATM_QUANTILE_DEFAULT = 25


class LmtPanel(Template):
    """Atmosphere conditions at the LMT.

    The panel publishes ``atm_model_name`` in its `site` store.

    Parameters
    ----------
    tel_surface_rms : astropy.units.Quantity
        RMS of the primary surface, shown for reference.
    """

    def __init__(self, tel_surface_rms: u.Quantity) -> None:
        super().__init__()
        card = self.child[dmc.Card](withBorder=True, padding="md")
        stack = card.child[dmc.Stack](gap="sm")
        stack.child[dmc.Title]("Site: Large Millimeter Telescope", order=5)
        self._atm = stack.child[dmc.SegmentedControl](
            data=[{"label": f"{q} %", "value": str(q)} for q in _ATM_QUANTILES],
            value=str(_ATM_QUANTILE_DEFAULT),
            size="xs",
        )
        stack.child[dmc.Text](
            "Atmosphere quantile of the am model; lower is drier. "
            f"Primary surface RMS: {tel_surface_rms.to_value(u.um):g} µm.",
            size="xs",
            c="dimmed",
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
