"""Telescope trajectory of the observation in three frames."""

from __future__ import annotations

from typing import TYPE_CHECKING

import astropy.units as u
import dash_mantine_components as dmc
import plotly.graph_objects as go
from dash import dcc
from dash_component_template import Template

if TYPE_CHECKING:
    from tolteca_simu.planning import Trajectory
    from tolteca_simu.toltec import Footprint

__all__ = ["TrajectoryPanel", "empty_figure", "make_trajectory_figures"]

_OFFSET_AXES = {
    "altaz": ("Delta-Source Az [arcmin]", "Delta-Source Alt [arcmin]"),
    "icrs": ("Delta-Source RA [arcmin]", "Delta-Source Dec [arcmin]"),
}


def _line(x: u.Quantity, y: u.Quantity, unit: u.Unit, color: str) -> go.Scattergl:
    return go.Scattergl(
        x=x.to_value(unit),
        y=y.to_value(unit),
        mode="lines",
        line={"color": color},
        showlegend=False,
    )


_DETECTOR_MARKERS = {0: "cross", 1: "x"}


def empty_figure() -> go.Figure:
    """Return an empty figure in the planner's style.

    Returns
    -------
    plotly.graph_objects.Figure
        A figure without data.
    """
    return go.Figure(layout={"template": "simple_white"})


def make_trajectory_figures(
    trajectory: Trajectory,
    ref_frame: str,
    footprint: Footprint | None = None,
    footprint_name: str = "",
) -> dict[str, go.Figure]:
    """Plot the boresight offsets, horizon track, and sky track.

    Parameters
    ----------
    trajectory : tolteca_simu.planning.Trajectory
        The trajectory to plot.
    ref_frame : {"altaz", "icrs"}
        Frame of the pattern offsets, which labels the offset axes.
    footprint : tolteca_simu.toltec.Footprint, optional
        Detectors to overlay on the offsets, marked by polarization group.
    footprint_name : str, optional
        Legend name of the footprint.

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
    if footprint is not None:
        for i, (pg, symbol) in enumerate(_DETECTOR_MARKERS.items()):
            mask = footprint.pg == pg
            figures["offset"].add_scattergl(
                x=footprint.dlon[mask].to_value(u.arcmin),
                y=footprint.dlat[mask].to_value(u.arcmin),
                mode="markers",
                marker={"symbol": symbol, "color": "gray", "size": 6},
                legendgroup="footprint",
                showlegend=i == 0,
                name=f"Toggle FOV: {footprint_name}",
            )
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
    return figures


class TrajectoryPanel(Template):
    """Boresight trajectory figures; filled by the planner page."""

    def __init__(self) -> None:
        super().__init__()
        card = self.child[dmc.Card](withBorder=True, padding="md")
        stack = card.child[dmc.Stack](gap="sm")
        stack.child[dmc.Title]("Trajectory", order=5)
        grid = stack.child[dmc.SimpleGrid](cols={"base": 1, "lg": 3})
        self.graphs = {
            key: grid.child[dcc.Graph](
                figure=empty_figure(), config={"displaylogo": False}
            )
            for key in ("offset", "altaz", "icrs")
        }
