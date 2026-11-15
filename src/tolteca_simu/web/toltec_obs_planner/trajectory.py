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

__all__ = [
    "FIGURE_LAYOUT",
    "TrajectoryPanel",
    "empty_figure",
    "make_trajectory_figures",
]

_AXIS = {
    "showline": True,
    "showgrid": False,
    "showticklabels": True,
    "linecolor": "black",
    "linewidth": 4,
    "ticks": "outside",
}
FIGURE_LAYOUT = {
    "xaxis": _AXIS,
    "yaxis": _AXIS,
    "plot_bgcolor": "white",
    "margin": {"autoexpand": True, "l": 0, "r": 10, "b": 0, "t": 10},
    "modebar": {"orientation": "v"},
    "legend": {
        "orientation": "h",
        "x": 0.5,
        "y": 1.02,
        "xanchor": "center",
        "yanchor": "bottom",
        "bgcolor": "#dfdfdf",
    },
}
"""Layout of the planner's figures, as v1's: black axis lines with outside
ticks, no grid, a vertical mode bar, and the legend centered above the plot."""

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
    """Return an empty figure without axes, as v1's.

    Returns
    -------
    plotly.graph_objects.Figure
        A figure without data.
    """
    return go.Figure(layout={"xaxis": {"visible": False}, "yaxis": {"visible": False}})


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
        "offset": go.Figure(
            _line(trajectory.dlon, trajectory.dlat, u.arcmin, "red"),
            layout=FIGURE_LAYOUT,
        ),
        "altaz": go.Figure(
            [
                _line(altaz.az, altaz.alt, u.deg, "red"),
                _line(target.az, target.alt, u.deg, "blue"),
            ],
            layout=FIGURE_LAYOUT,
        ),
        "icrs": go.Figure(_line(icrs.ra, icrs.dec, u.deg, "red"), layout=FIGURE_LAYOUT),
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
            title_text=x_title,
            automargin=True,
            autorange="reversed",
            scaleanchor="y",
            scaleratio=1,
        )
        fig.update_yaxes(title_text=y_title, automargin=True)
    return figures


class TrajectoryPanel(Template):
    """Target altitude and boresight trajectory figures, in a row as in v1.

    The planner page fills the `graphs`: ``visibility`` (from
    `make_visibility_figure`), then ``offset``, ``altaz`` and ``icrs`` (from
    `make_trajectory_figures`).
    """

    def __init__(self) -> None:
        super().__init__()
        grid = self.child[dmc.SimpleGrid](cols={"base": 1, "sm": 2, "lg": 4})
        self.graphs = {
            key: grid.child[dcc.Graph](
                figure=empty_figure(), config={"displaylogo": False}
            )
            for key in ("visibility", "offset", "altaz", "icrs")
        }
