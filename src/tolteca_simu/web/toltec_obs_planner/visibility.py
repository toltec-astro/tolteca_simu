"""Target elevation over the observing day."""

from __future__ import annotations

from typing import TYPE_CHECKING

import astropy.units as u
import numpy as np
import plotly.graph_objects as go

from .trajectory import FIGURE_LAYOUT

if TYPE_CHECKING:
    from astropy.time import Time

    from tolteca_simu.planning import TargetVisibility

__all__ = ["make_visibility_figure"]


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
    fig = go.Figure(layout=FIGURE_LAYOUT)
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
    fig.update_xaxes(title_text="Time [UT]", automargin=True)
    fig.update_yaxes(
        title_text="Target Altitude [deg]", automargin=True, range=[-10, 90]
    )
    return fig
