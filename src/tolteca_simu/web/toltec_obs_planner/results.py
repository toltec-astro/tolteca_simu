"""TolTEC coverage and sensitivity views."""

from __future__ import annotations

from typing import TYPE_CHECKING

import astropy.units as u
import dash_mantine_components as dmc
import numpy as np
import plotly.graph_objects as go
from dash import dcc
from dash_component_template import Template

from tolteca_simu.toltec import TOLTEC_ARRAYS

if TYPE_CHECKING:
    from tolteca_simu.toltec.planning import ToltecPlanningResult
    from tolteca_simu.toltec.time_cost import TimeCost

__all__ = ["ToltecResultsPanel", "make_coverage_figure", "make_sensitivity_tabs"]

_DISPLAY_SIZE_MAX = 600
# Values below this fraction of the maximum are FFT round-off.
_COVERED_FRACTION = 1e-6


def _fmt(value: object) -> str:
    if isinstance(value, u.Quantity):
        return f"{value.value:.3g} {value.unit:unicode}"
    return str(value)


def make_coverage_figure(result: ToltecPlanningResult, unit: str) -> go.Figure:
    """Plot the coverage of the computed array.

    The image is cropped to the covered pixels and decimated to at most 600
    pixels on a side for display.

    Parameters
    ----------
    result : tolteca_simu.toltec.planning.ToltecPlanningResult
        The TolTEC results.
    unit : {"depth", "time"}
        Plot map depth (mJy/beam) or coverage (s/pixel), without turnarounds.

    Returns
    -------
    plotly.graph_objects.Figure
        Heatmap with RA and Dec axes along the image center lines.
    """
    data = result.depth.depth if unit == "depth" else result.coverage.data_on_scan
    covered = data > _COVERED_FRACTION * data.max()
    rows = np.flatnonzero(covered.any(axis=1))
    cols = np.flatnonzero(covered.any(axis=0))
    step = int(np.ceil(max(rows.size, cols.size) / _DISPLAY_SIZE_MAX))
    y = np.arange(rows[0], rows[-1] + 1, step)
    x = np.arange(cols[0], cols[-1] + 1, step)
    image = np.where(covered, data, np.nan)[np.ix_(y, x)]
    wcs = result.coverage.wcs
    ra, _ = wcs.pixel_to_world_values(x, np.full(x.shape, y.mean()))
    _, dec = wcs.pixel_to_world_values(np.full(y.shape, x.mean()), y)
    title = "Depth [mJy/beam]" if unit == "depth" else "Coverage [s/pixel]"
    fig = go.Figure(
        go.Heatmap(
            x=ra,
            y=dec,
            z=image,
            colorscale="Viridis",
            colorbar={"title": {"text": title}},
        )
    )
    fig.update_xaxes(title_text="RA [deg]", autorange="reversed")
    fig.update_yaxes(title_text="Dec [deg]", scaleanchor="x", scaleratio=1)
    fig.update_layout(
        template="simple_white", margin={"l": 10, "r": 10, "b": 10, "t": 10}
    )
    return fig


def make_sensitivity_tabs(
    result: ToltecPlanningResult, time_cost: TimeCost
) -> dmc.Tabs:
    """Tabulate the sensitivity of each array and the project time.

    Parameters
    ----------
    result : tolteca_simu.toltec.planning.ToltecPlanningResult
        The TolTEC results.
    time_cost : tolteca_simu.toltec.time_cost.TimeCost
        The project time.

    Returns
    -------
    dash_mantine_components.Tabs
        One table per array, the computed array selected.
    """
    stokes = "Polarized (Q/U)" if result.polarized else "Total Intensity (I)"
    panels = []
    for name, s in result.summaries.items():
        rows = [
            ("Array", name),
            ("Mean altitude", s.alt_mean.to(u.deg)),
            (
                "Detectors (enabled / designed)",
                (
                    f"{s.n_dets} / {s.n_dets_designed} "
                    f"({s.n_dets / s.n_dets_designed:.0%})"
                ),
            ),
            (f"Detector sensitivity ({stokes})", s.detector_sensitivity),
            (
                f"Mapping speed ({stokes})",
                f"{s.mapping_speed.value:.1f} {s.mapping_speed.unit:unicode}",
            ),
            ("Map area", result.depth.map_area),
            ("Exposure time per pass", result.t_exp),
            ("On-target time per pass", result.t_exp_eff),
            ("Depth Stokes parameters", stokes),
            ("Median RMS depth per pass", s.depth_rms),
            ("Number of passes", result.n_passes),
            ("Coadded RMS depth", s.depth_rms_coadd),
            ("Project science time", time_cost.science_time),
            ("Science time overhead", time_cost.science_overhead),
            (
                "Observing nights",
                (
                    f"{time_cost.n_nights} "
                    f"(at {time_cost.science_time_per_night:g} of science per night)"
                ),
            ),
            ("Project total time (incl. overhead)", time_cost.total_time),
            ("Project overhead", time_cost.overhead_time),
            ("Project overhead %", f"{time_cost.overhead_fraction:.1%}"),
        ]
        panels.append(
            dmc.TabsPanel(
                dmc.Table(
                    data={"body": [[label, _fmt(value)] for label, value in rows]},
                    striped=True,
                    highlightOnHover=True,
                    fz="xs",
                ),
                value=name,
            )
        )
    return dmc.Tabs(
        [
            dmc.TabsList(
                [
                    dmc.TabsTab(f"{TOLTEC_ARRAYS[name].wl_center:g}", value=name)
                    for name in result.summaries
                ]
            ),
            *panels,
        ],
        value=result.array_name,
    )


class ToltecResultsPanel(Template):
    """Coverage map and sensitivity tables; filled by the planner page."""

    def __init__(self) -> None:
        super().__init__()
        card = self.child[dmc.Card](withBorder=True, padding="md")
        stack = card.child[dmc.Stack](gap="sm")
        stack.child[dmc.Title]("TolTEC coverage and sensitivity", order=5)
        self.status = stack.child[dmc.Text](size="xs", c="dimmed")
        grid = stack.child[dmc.SimpleGrid](cols={"base": 1, "lg": 2})
        self.coverage = grid.child[dcc.Graph](
            figure=go.Figure(layout={"template": "simple_white"}),
            config={"displaylogo": False},
        )
        self.sensitivity = grid.child[dmc.Box]()
