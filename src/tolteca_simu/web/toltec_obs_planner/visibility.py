"""Target elevation over the observing day."""

from __future__ import annotations

from typing import TYPE_CHECKING

import astropy.units as u
import dash_mantine_components as dmc
import numpy as np
import plotly.graph_objects as go
from dash import Input, Output, dcc
from dash_component_template import Template

from tolteca_simu.lmt import get_lmt_observer
from tolteca_simu.planning import ObservationDescription, get_target_visibility

if TYPE_CHECKING:
    from astropy.time import Time
    from dash import Dash
    from dash_component_template import LazyComponent

    from tolteca_simu.planning import TargetVisibility

__all__ = ["VisibilityPanel", "make_visibility_figure"]


def make_visibility_figure(
    visibility: TargetVisibility, t1: Time, target_alt_min: u.Quantity
) -> go.Figure:
    """Plot target altitude over the day, split into daytime and night.

    Parameters
    ----------
    visibility : tolteca_simu.planning.TargetVisibility
        Altitudes over the observing day.
    t1 : astropy.time.Time
        End of the observation, marked from the start time.
    target_alt_min : astropy.units.Quantity
        Lowest usable elevation; lower altitudes are shaded.

    Returns
    -------
    plotly.graph_objects.Figure
        Altitude against UT, with the observation interval marked.
    """
    jd = visibility.time.jd
    i_rise = np.searchsorted(jd, visibility.sun_rise_time.jd, side="left") - 1
    i_set = np.searchsorted(jd, visibility.sun_set_time.jd, side="right")
    if i_rise < i_set:
        b0, b1, is_daytime = i_rise, i_set, [False, True, False]
    else:
        b0, b1, is_daytime = i_set, i_rise, [True, False, True]
    segments = [slice(None, b0), slice(b0, b1 + 1), slice(b1 + 1, None)]
    show_legend = [True, True, False] if b0 > 0 else [False, True, True]
    x = visibility.time.to_datetime()
    alt = visibility.alt.to_value(u.deg)
    fig = go.Figure()
    for s, daytime, showlegend in zip(segments, is_daytime, show_legend, strict=True):
        fig.add_scatter(
            x=x[s],
            y=alt[s],
            mode="lines",
            line={"color": "orange" if daytime else "blue"},
            name="Daytime" if daytime else "Night",
            legendgroup="daytime" if daytime else "night",
            showlegend=showlegend,
        )
    i_t0 = np.searchsorted(jd, visibility.t0.jd, side="left") - 1
    i_t1 = np.searchsorted(jd, t1.jd, side="right")
    fig.add_scatter(
        x=x[i_t0:i_t1],
        y=alt[i_t0:i_t1],
        mode="markers",
        marker={"color": "red", "size": 8},
        name="Target",
    )
    fig.add_hrect(
        y0=-90,
        y1=target_alt_min.to_value(u.deg),
        line_width=1,
        fillcolor="gray",
        opacity=0.2,
    )
    fig.update_xaxes(title_text="Time [UT]")
    fig.update_yaxes(title_text="Target Altitude [deg]", range=[-10, 90])
    fig.update_layout(
        template="simple_white",
        margin={"l": 10, "r": 10, "b": 10, "t": 10},
        legend={
            "orientation": "h",
            "x": 0.5,
            "y": 1.02,
            "xanchor": "center",
            "yanchor": "bottom",
        },
    )
    return fig


class VisibilityPanel(Template):
    """Check of the target at the start time, and its elevation over the day.

    The check shows in the panel; the elevation plot opens in a modal, as in
    v1.

    Parameters
    ----------
    description : dash_component_template.LazyComponent
        Store holding the serialized observation description, or None.
    target_alt_min : astropy.units.Quantity
        Lowest usable elevation.
    """

    def __init__(self, description: LazyComponent, target_alt_min: u.Quantity) -> None:
        super().__init__()
        self._description = description
        self._target_alt_min = target_alt_min
        stack = self.child[dmc.Stack](gap="xs")
        self._status = stack.child[dmc.Text](
            "Enter a target and an observation time.", size="xs", c="gray"
        )
        self._plot_button = stack.child[dmc.Button](
            "Plot alt. vs time", size="xs", variant="light", disabled=True
        )
        self._modal = stack.child[dmc.Modal](
            title="Target altitude", size="xl", opened=False
        )
        self._graph = self._modal.child[dcc.Graph](
            figure=go.Figure(layout={"template": "simple_white"}),
            config={"displaylogo": False},
        )

    def setup_callbacks(self, app: Dash) -> None:
        """Plot the visibility of the current description.

        Parameters
        ----------
        app : dash.Dash
            Application receiving the callbacks.
        """
        app.clientside_callback(
            "function(_n_clicks) { return true; }",
            Output(self._modal(), "opened"),
            Input(self._plot_button(), "n_clicks"),
            prevent_initial_call=True,
        )

        @app.callback(
            Output(self._graph(), "figure"),
            Output(self._status(), "children"),
            Output(self._status(), "c"),
            Output(self._plot_button(), "disabled"),
            Input(self._description(), "data"),
            prevent_initial_call=True,
        )
        def _plot(data: dict | None) -> tuple[go.Figure, str, str, bool]:
            if data is None:
                return (
                    go.Figure(layout={"template": "simple_white"}),
                    "Enter a target and an observation time.",
                    "gray",
                    True,
                )
            description = ObservationDescription.model_validate(data)
            visibility = get_target_visibility(
                description.target, description.t0, get_lmt_observer()
            )
            figure = make_visibility_figure(
                visibility,
                description.t0 + description.get_t_exp(),
                self._target_alt_min,
            )
            message, color = self._check(visibility)
            return figure, message, color, False

    def _check(self, visibility: TargetVisibility) -> tuple[str, str]:
        altaz = visibility.altaz_t0
        position = f"Az = {altaz.az.degree:.4f}d, Alt = {altaz.alt.degree:.4f}d"
        if not visibility.is_night_t0:
            rise = visibility.sun_rise_time.iso[:19]
            set_ = visibility.sun_set_time.iso[:19]
            message = (
                f"The start time is not at night (sunrise {rise}, sunset {set_}). "
                f"Target {position}."
            )
            return message, "orange"
        if altaz.alt < self._target_alt_min:
            return (
                f"Target {position} is below {self._target_alt_min:.0f}.",
                "red",
            )
        return f"Target {position}.", "green"
