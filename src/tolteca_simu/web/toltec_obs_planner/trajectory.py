"""Telescope trajectory of the observation in three frames."""

from __future__ import annotations

from typing import TYPE_CHECKING

import astropy.units as u
import dash_mantine_components as dmc
import plotly.graph_objects as go
from dash import Input, Output, dcc
from dash_component_template import Template

from tolteca_simu.lmt import get_lmt_observer
from tolteca_simu.planning import ObservationDescription, get_trajectory

if TYPE_CHECKING:
    from dash import Dash
    from dash_component_template import LazyComponent

    from tolteca_simu.planning import Trajectory

__all__ = ["TrajectoryPanel", "make_trajectory_figures"]

_OFFSET_AXES = {
    "altaz": ("Delta-Source Az [arcmin]", "Delta-Source Alt [arcmin]"),
    "icrs": ("Delta-Source RA [arcmin]", "Delta-Source Dec [arcmin]"),
}


def _empty_figure() -> go.Figure:
    return go.Figure(layout={"template": "simple_white"})


def _line(x: u.Quantity, y: u.Quantity, unit: u.Unit, color: str) -> go.Scattergl:
    return go.Scattergl(
        x=x.to_value(unit),
        y=y.to_value(unit),
        mode="lines",
        line={"color": color},
        showlegend=False,
    )


def make_trajectory_figures(
    trajectory: Trajectory, ref_frame: str
) -> dict[str, go.Figure]:
    """Plot the boresight offsets, horizon track, and sky track.

    Parameters
    ----------
    trajectory : tolteca_simu.planning.Trajectory
        The trajectory to plot.
    ref_frame : {"altaz", "icrs"}
        Frame of the pattern offsets, which labels the offset axes.

    Returns
    -------
    dict of plotly.graph_objects.Figure
        Figures keyed ``offset``, ``altaz`` (with the target track in blue) and
        ``icrs``, with longitude increasing to the left and equal axis scales.
    """
    altaz = trajectory.coords_altaz
    icrs = trajectory.coords_icrs
    target = trajectory.target_altaz
    figures = {
        "offset": go.Figure(_line(trajectory.dlon, trajectory.dlat, u.arcmin, "red")),
        "altaz": go.Figure(
            [
                _line(altaz.az, altaz.alt, u.deg, "red"),
                _line(target.az, target.alt, u.deg, "blue"),
            ]
        ),
        "icrs": go.Figure(_line(icrs.ra, icrs.dec, u.deg, "red")),
    }
    axes = {
        "offset": _OFFSET_AXES[ref_frame],
        "altaz": ("Azimuth [deg]", "Altitude [deg]"),
        "icrs": ("RA [deg]", "Dec [deg]"),
    }
    for key, fig in figures.items():
        x_title, y_title = axes[key]
        fig.update_xaxes(
            title_text=x_title, autorange="reversed", scaleanchor="y", scaleratio=1
        )
        fig.update_yaxes(title_text=y_title)
        fig.update_layout(
            template="simple_white", margin={"l": 10, "r": 10, "b": 10, "t": 10}
        )
    return figures


class TrajectoryPanel(Template):
    """Boresight trajectory of the current description.

    Parameters
    ----------
    description : dash_component_template.LazyComponent
        Store holding the serialized observation description, or None.
    """

    def __init__(self, description: LazyComponent) -> None:
        super().__init__()
        self._description = description
        card = self.child[dmc.Card](withBorder=True, padding="md")
        stack = card.child[dmc.Stack](gap="sm")
        stack.child[dmc.Title]("Trajectory", order=5)
        grid = stack.child[dmc.SimpleGrid](cols={"base": 1, "lg": 3})
        self._graphs = {
            key: grid.child[dcc.Graph](
                figure=_empty_figure(), config={"displaylogo": False}
            )
            for key in ("offset", "altaz", "icrs")
        }

    def setup_callbacks(self, app: Dash) -> None:
        """Plot the trajectory of the current description.

        Parameters
        ----------
        app : dash.Dash
            Application receiving the callbacks.
        """

        @app.callback(
            [Output(graph(), "figure") for graph in self._graphs.values()],
            Input(self._description(), "data"),
            prevent_initial_call=True,
        )
        def _plot(data: dict | None) -> list[go.Figure]:
            if data is None:
                return [_empty_figure() for _ in self._graphs]
            description = ObservationDescription.model_validate(data)
            trajectory = get_trajectory(
                description.mapping,
                description.target,
                description.t0,
                t_exp=description.get_t_exp(),
                ref_frame=description.ref_frame,
                observer=get_lmt_observer(),
            )
            figures = make_trajectory_figures(trajectory, description.ref_frame)
            return [figures[key] for key in self._graphs]
