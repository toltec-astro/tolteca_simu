"""TolTEC sensitivity view."""

from __future__ import annotations

from typing import TYPE_CHECKING

import astropy.units as u
import dash_mantine_components as dmc
from dash_component_template import Template

from tolteca_simu.toltec import TOLTEC_ARRAYS

if TYPE_CHECKING:
    from tolteca_simu.toltec.planning import ToltecPlanningResult
    from tolteca_simu.toltec.time_cost import TimeCost

__all__ = ["ToltecResultsPanel", "make_sensitivity_tabs"]


def _fmt(value: object) -> str:
    if isinstance(value, u.Quantity):
        return f"{value.value:.3g} {value.unit:unicode}"
    return str(value)


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
    """Sensitivity tables; filled by the planner page."""

    def __init__(self) -> None:
        super().__init__()
        card = self.child[dmc.Card](withBorder=True, padding="md")
        stack = card.child[dmc.Stack](gap="sm")
        stack.child[dmc.Title]("TolTEC sensitivity", order=5)
        self.status = stack.child[dmc.Text](size="xs", c="dimmed")
        self.sensitivity = stack.child[dmc.Box]()
